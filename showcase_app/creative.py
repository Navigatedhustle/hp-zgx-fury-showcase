"""One CPU-offloaded creative owner, called only by the single image-service worker."""
import io
import base64
import time
import subprocess
import ctypes
import ctypes.util
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAN = ROOT / 'models/Wan2.2-TI2V-5B-Diffusers'
CREATIVE_CONFIG = json.loads((ROOT / 'config/creative-models.json').read_text())
VIDEO_PROFILE = CREATIVE_CONFIG.get('candidate_profile', 'base')
VIDEO_MODEL = 'Wan2.2-TI2V-5B' + (' + LongLive-Plug few-step 1.0 / CFG 0.5' if VIDEO_PROFILE == 'longlive' else '')


def fuse_longlive(transformer):
    """Fuse the pinned, same-backbone Apache-2.0 adapters on Grace, once."""
    import torch
    from safetensors.torch import load_file
    from diffusers.loaders.lora_conversion_utils import _convert_non_diffusers_wan_lora_to_diffusers
    states = []
    for entry, scale in zip(CREATIVE_CONFIG['reviewed_adapters'], (1.0, .5)):
        folder = ROOT / 'models' / entry['repo'].split('/')[-1]
        path = folder / 'adapter_model.safetensors'
        expected = next(f['sha256'] for f in entry['files'] if f['path'] == path.name)
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise RuntimeError('Pinned video adapter checksum failed')
        raw = load_file(str(path), device='cpu')
        if len(raw) != 600 or not all(k.startswith('base_model.model.blocks.') for k in raw):
            raise RuntimeError('Unexpected video adapter architecture')
        original = {'diffusion_model.' + k.removeprefix('base_model.model.'): v for k, v in raw.items()}
        states.append((_convert_non_diffusers_wan_lora_to_diffusers(original), scale))
    modules = {k.removesuffix('.lora_A.weight').removeprefix('transformer.') for k in states[0][0] if k.endswith('.lora_A.weight')}
    if len(modules) != 300 or any(set(state) != set(states[0][0]) for state, _ in states):
        raise RuntimeError('Video adapters do not cover the matching 300 linear modules')
    with torch.no_grad():
        for name in sorted(modules):
            weight = transformer.get_submodule(name).weight
            if weight.device.type != 'cpu':
                raise RuntimeError('Video adapters must be fused on Grace before GPU offload')
            merged = weight.float()
            for state, scale in states:
                a, b = (state['transformer.' + name + '.lora_' + suffix + '.weight'] for suffix in ('A', 'B'))
                delta = b.float() @ a.float()
                if delta.shape != weight.shape:
                    raise RuntimeError('Video adapter shape mismatch')
                merged = merged + scale * delta
            if not torch.isfinite(merged).all():
                raise RuntimeError('Nonfinite fused video weights')
            weight.copy_(merged.to(weight.dtype))


def bind_grace():
    """Bind this calling thread's future CPU allocations, never host-wide policy."""
    nodes = [path for path in Path('/sys/devices/system/node').glob('node[0-9]*') if (path / 'cpulist').read_text().strip()]
    if len(nodes) != 1:
        raise RuntimeError('Cannot identify the tested single Grace CPU NUMA node')
    node = int(nodes[0].name[4:])
    lib = ctypes.CDLL(ctypes.util.find_library('numa'), use_errno=True)
    fn = lib.set_mempolicy
    fn.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ulong), ctypes.c_ulong]
    fn.restype = ctypes.c_int
    mask = ctypes.c_ulong(1 << node)
    if fn(2, ctypes.byref(mask), ctypes.sizeof(mask) * 8) != 0:
        raise OSError(ctypes.get_errno(), 'Could not bind creative CPU allocations to Grace')
    return node


def copy_cpu_weights(pipeline):
    """Materialize CPU weights on Grace, instead of HBM-backed file-cache mappings."""
    import torch
    for component in pipeline.components.values():
        if isinstance(component, torch.nn.Module):
            for tensor in list(component.parameters()) + list(component.buffers()):
                if tensor.device.type != 'cpu':
                    raise RuntimeError('Expected CPU weights before configuring creative offload')
                tensor.data = tensor.data.clone()


def export_frames(frames, path, stop, job=None):
    import numpy as np
    from imageio_ffmpeg import get_ffmpeg_exe
    height, width = frames[0].shape[:2]
    process = subprocess.Popen([get_ffmpeg_exe(), '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', '24', '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-threads', '4', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for index,frame in enumerate(frames):
            if stop.is_set():
                raise InterruptedError('Creative job cancelled')
            pixels = frame if frame.dtype == np.uint8 else np.clip(frame * 255, 0, 255).astype(np.uint8)
            process.stdin.write(np.ascontiguousarray(pixels).tobytes())
            if job is not None:job['frames_encoded']=index+1
        process.stdin.close()
        error = process.stderr.read()
        if process.wait() != 0:
            raise RuntimeError('Local video assembly failed: ' + error.decode(errors='replace')[:300])
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


def reference_image(data):
    from PIL import Image
    if not data.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
        raise ValueError('Expected a PNG, JPEG or WebP data image')
    raw = base64.b64decode(data.split(',', 1)[1], validate=True)
    if len(raw) > 8 * 1024 ** 2:
        raise ValueError('Reference image exceeds 8 MiB')
    try:source=Image.open(io.BytesIO(raw),formats=['PNG','JPEG','WEBP'])
    except Image.DecompressionBombError:raise ValueError('Reference image exceeds its pixel bound') from None
    with source:
        expected={'data:image/png;base64,':'PNG','data:image/jpeg;base64,':'JPEG','data:image/webp;base64,':'WEBP'}
        if source.format!=next(kind for prefix,kind in expected.items() if data.startswith(prefix)):
            raise ValueError('Reference content does not match its image type')
        if source.width * source.height > 4 * 1024 ** 2:
            raise ValueError('Reference image exceeds four megapixels')
        return source.convert('RGB')


class CreativeLane:
    def __init__(self):
        self.flux = None
        self.wan = None
        self.wan_text = None

    def load(self):
        self.grace_node = bind_grace()
        import torch
        torch.set_num_threads(8)
        from diffusers import Flux2KleinPipeline
        self.flux = Flux2KleinPipeline.from_pretrained(str(ROOT / 'models/FLUX.2-klein-4B'), torch_dtype=torch.bfloat16, local_files_only=True)
        copy_cpu_weights(self.flux)
        self.flux.enable_model_cpu_offload()
        if (WAN / 'model_index.json').is_file():
            from diffusers.pipelines.wan.pipeline_wan_i2v import prompt_clean
            if prompt_clean('A &amp; B') != 'A & B':
                raise RuntimeError('Wan prompt normalization failed its startup check')
            self.load_video()
        elif VIDEO_PROFILE == 'longlive':
            raise RuntimeError('Selected video assets are missing; run ./launch.sh setup')

    def load_video(self):
        if self.wan is not None:
            return
        import torch
        from diffusers import AutoencoderKLWan, WanImageToVideoPipeline, WanPipeline
        vae = AutoencoderKLWan.from_pretrained(str(WAN), subfolder='vae', torch_dtype=torch.float32, local_files_only=True)
        self.wan = WanImageToVideoPipeline.from_pretrained(str(WAN), vae=vae, torch_dtype=torch.bfloat16, image_encoder=None, image_processor=None, local_files_only=True)
        copy_cpu_weights(self.wan)
        if VIDEO_PROFILE == 'longlive':
            fuse_longlive(self.wan.transformer)
        self.wan.vae.enable_tiling()
        self.wan_text=WanPipeline(vae=self.wan.vae,text_encoder=self.wan.text_encoder,tokenizer=self.wan.tokenizer,transformer=self.wan.transformer,scheduler=self.wan.scheduler,expand_timesteps=True)
        self.wan.enable_model_cpu_offload()

    def run(self, kind, prompt, path, stop, options, job):
        bind_grace()
        import torch
        if kind == 'video':
            began = time.monotonic()
            self.load_video()
            job['model_load_seconds'] = time.monotonic() - began
        # Bound this process, leaving the 10 GiB reserve plus a 4 GiB guard.
        # Existing text engines and their fractions/contexts/slots are untouched.
        torch.cuda.empty_cache()
        free, total = torch.cuda.mem_get_info()
        budget = torch.cuda.memory_reserved() + free - 14 * 1024 ** 3
        if budget <= 0:
            raise RuntimeError('Insufficient measured HBM above the creative reserve guard')
        torch.cuda.set_per_process_memory_fraction(min(.95, budget / total))
        torch.cuda.reset_peak_memory_stats()
        job['allocator_budget_bytes'] = budget
        pipeline = (self.wan if options.get('reference') is not None else self.wan_text) if kind == 'video' else self.flux
        if kind == 'video':pipeline.enable_model_cpu_offload()
        steps = options.get('steps', 4 if VIDEO_PROFILE == 'longlive' else 50) if kind == 'video' else 4
        job.update(steps_done=0, steps_total=steps, width=options.get('width', 768), height=options.get('height', 768))
        if kind == 'video':job.update(profile=VIDEO_PROFILE, guidance=options.get('guidance', 1.0 if VIDEO_PROFILE == 'longlive' else 5.0))

        def checkpoint(pipe, step, timestep, kwargs):
            if stop.is_set():
                raise InterruptedError('Creative job cancelled')
            free_now, _ = torch.cuda.mem_get_info()
            if free_now < 11 * 1024 ** 3:
                raise InterruptedError('Creative guard stopped the job before the 10 GiB reserve')
            job['steps_done'] = step + 1
            return kwargs

        began = time.monotonic()
        try:
            job['stage']='Denoising'
            args = dict(prompt=prompt, height=job['height'], width=job['width'], num_inference_steps=steps, guidance_scale=job['guidance'] if kind == 'video' else 1.0, generator=torch.Generator('cuda').manual_seed(options.get('seed', 42)), callback_on_step_end=checkpoint)
            if options.get('reference') is not None:
                args['image'] = options['reference']
            if kind == 'video':
                args.update(num_frames=121)
                frames = pipeline(**args).frames[0]
                if stop.is_set():
                    raise InterruptedError('Creative job cancelled')
                if not path.parent.is_dir():raise InterruptedError('Session deleted; output discarded')
                job.update(stage='Encoding',frames_generated=len(frames),fps=24)
                export_frames(frames, path, stop,job)
            else:
                batch=options.get('batch',1)
                for index in range(batch):
                    args['generator']=torch.Generator('cuda').manual_seed(options.get('seed',42)+index)
                    job.update(stage=f'Image {index+1} of {batch}',batch_index=index+1)
                    picture=pipeline(**args).images[0]
                    if stop.is_set():raise InterruptedError('Creative job cancelled')
                    if not path.parent.is_dir():raise InterruptedError('Session deleted; output discarded')
                    target=path if batch==1 else path.with_stem(path.stem+'-'+str(index+1))
                    picture.save(target);picture.close()
                    job['images_done']=index+1
                    if not job.get('_private'):job.setdefault('urls',[]).append('/images/'+target.name)
            torch.cuda.synchronize()
            return {'render_seconds': time.monotonic() - began, 'gpu_peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'gpu_peak_reserved_bytes': torch.cuda.max_memory_reserved()}
        finally:
            job.update(render_seconds=time.monotonic() - began, gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(), gpu_peak_reserved_bytes=torch.cuda.max_memory_reserved())
            pipeline.maybe_free_model_hooks()
            torch.cuda.empty_cache()

    def placement(self):
        def device(module):
            return str(next(module.parameters()).device) if module is not None else 'not loaded'
        return {'flux_loaded': self.flux is not None, 'video_loaded': self.wan is not None, 'video_profile': VIDEO_PROFILE, 'video_model': VIDEO_MODEL, 'flux_transformer': device(self.flux.transformer) if self.flux else 'not loaded', 'video_transformer': device(self.wan.transformer) if self.wan else 'not loaded', 'grace_cpu_node': self.grace_node, 'policy': 'Resident CPU-offloaded models bound to Grace; one active GPU job across images and video'}

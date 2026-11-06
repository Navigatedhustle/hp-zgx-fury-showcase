"""One CPU-offloaded creative owner, called only by the single image-service worker."""
import io
import base64
import time
import subprocess
import ctypes
import ctypes.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAN = ROOT / 'models/Wan2.2-TI2V-5B-Diffusers'


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


def export_frames(frames, path, stop):
    import numpy as np
    from imageio_ffmpeg import get_ffmpeg_exe
    height, width = frames[0].shape[:2]
    process = subprocess.Popen([get_ffmpeg_exe(), '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', '24', '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-threads', '4', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for frame in frames:
            if stop.is_set():
                raise InterruptedError('Creative job cancelled')
            pixels = frame if frame.dtype == np.uint8 else np.clip(frame * 255, 0, 255).astype(np.uint8)
            process.stdin.write(np.ascontiguousarray(pixels).tobytes())
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
    with Image.open(io.BytesIO(raw)) as source:
        if source.width * source.height > 4 * 1024 ** 2:
            raise ValueError('Reference image exceeds four megapixels')
        return source.convert('RGB')


class CreativeLane:
    def __init__(self):
        self.flux = None
        self.wan = None

    def load(self):
        self.grace_node = bind_grace()
        import torch
        from diffusers import Flux2KleinPipeline
        self.flux = Flux2KleinPipeline.from_pretrained(str(ROOT / 'models/FLUX.2-klein-4B'), torch_dtype=torch.bfloat16, local_files_only=True)
        copy_cpu_weights(self.flux)
        self.flux.enable_model_cpu_offload()
        if (WAN / 'model_index.json').is_file():
            from diffusers.pipelines.wan.pipeline_wan_i2v import prompt_clean
            if prompt_clean('A &amp; B') != 'A & B':
                raise RuntimeError('Wan prompt normalization failed its startup check')
            self.load_video()

    def load_video(self):
        if self.wan is not None:
            return
        import torch
        from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
        vae = AutoencoderKLWan.from_pretrained(str(WAN), subfolder='vae', torch_dtype=torch.float32, local_files_only=True)
        self.wan = WanImageToVideoPipeline.from_pretrained(str(WAN), vae=vae, torch_dtype=torch.bfloat16, image_encoder=None, image_processor=None, local_files_only=True)
        copy_cpu_weights(self.wan)
        self.wan.vae.enable_tiling()
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
        pipeline = self.wan if kind == 'video' else self.flux
        steps = options.get('steps', 50) if kind == 'video' else 4
        job.update(steps_done=0, steps_total=steps, width=options.get('width', 768), height=options.get('height', 768))

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
            args = dict(prompt=prompt, height=job['height'], width=job['width'], num_inference_steps=steps, guidance_scale=options.get('guidance', 5.0) if kind == 'video' else 1.0, generator=torch.Generator('cuda').manual_seed(options.get('seed', 42)), callback_on_step_end=checkpoint)
            if options.get('reference') is not None:
                args['image'] = options['reference']
            if kind == 'video':
                args.update(num_frames=121)
                frames = pipeline(**args).frames[0]
                if stop.is_set():
                    raise InterruptedError('Creative job cancelled')
                export_frames(frames, path, stop)
                job.update(frames_generated=len(frames), fps=24)
            else:
                picture = pipeline(**args).images[0]
                if stop.is_set():
                    raise InterruptedError('Creative job cancelled')
                picture.save(path)
            torch.cuda.synchronize()
            return {'render_seconds': time.monotonic() - began, 'gpu_peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'gpu_peak_reserved_bytes': torch.cuda.max_memory_reserved()}
        finally:
            job.update(render_seconds=time.monotonic() - began, gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(), gpu_peak_reserved_bytes=torch.cuda.max_memory_reserved())
            pipeline.maybe_free_model_hooks()
            torch.cuda.empty_cache()

    def placement(self):
        def device(module):
            return str(next(module.parameters()).device) if module is not None else 'not loaded'
        return {'flux_loaded': self.flux is not None, 'video_loaded': self.wan is not None, 'flux_transformer': device(self.flux.transformer) if self.flux else 'not loaded', 'video_transformer': device(self.wan.transformer) if self.wan else 'not loaded', 'grace_cpu_node': self.grace_node, 'policy': 'Resident CPU-offloaded models bound to Grace; one active GPU job across images and video'}

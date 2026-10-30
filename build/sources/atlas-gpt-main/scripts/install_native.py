import urllib.request
import tarfile
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def archive(url, destination, checksum=False):
    name=url.rsplit('/',1)[1]
    target=ROOT/'vendor'/name
    print('Downloading', name, flush=True)
    urllib.request.urlretrieve(url,target)
    if checksum:
        expected=urllib.request.urlopen(url+'.sha256').read().decode().split()[0]
        actual=hashlib.file_digest(target.open('rb'),'sha256').hexdigest()
        assert actual==expected, 'Checksum mismatch'
    destination.mkdir(parents=True,exist_ok=True)
    with tarfile.open(target) as tar: tar.extractall(destination,filter='data')
    print('Installed',destination,flush=True)
archive('https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/nightly/nemo-speech-nightly-linux-aarch64-cuda13.tar.gz',ROOT/'vendor'/'speech',True)
archive('https://github.com/ggml-org/llama.cpp/releases/download/b11490/llama-b11490-bin-ubuntu-cuda-13.4-arm64.tar.gz',ROOT/'vendor'/'llama')

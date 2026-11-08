"""Actual font rendering with host font discovery deliberately unavailable."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import unicodedata
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]


def test_translation_pdf_embeds_fonts_without_installed_host_fonts(tmp_path,monkeypatch):
    from showcase_app.workloads import export_document
    config=tmp_path/'empty.conf';config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig></fontconfig>')
    monkeypatch.setenv('FONTCONFIG_FILE',str(config))
    asyncio.run(export_document(tmp_path,['Fictional English. العربية עברית हिन्दी বাংলা தமிழ் తెలుగు ไทย 日本語 中文 한국어'],'Japanese'))
    reader=PdfReader(tmp_path/'translated.pdf')
    names=[]
    for page in reader.pages:
        for font in page['/Resources'].get('/Font',{}).values():
            font=font.get_object()
            name=str(font.get('/BaseFont',''))
            if name:names.append(name)
            else:assert font.get('/Subtype')=='/Type3' and len(font.get('/CharProcs',{}))>0
    assert names and all('Noto' in name for name in names),names
    text=unicodedata.normalize('NFKC', ''.join(page.extract_text() for page in reader.pages))
    assert '日本語' in text and '한국어' in text


def test_trailer_title_uses_packaged_font_in_an_empty_host_font_namespace(tmp_path):
    command=['bwrap','--unshare-all','--die-with-parent','--clearenv','--setenv','OPENBLAS_NUM_THREADS','1','--setenv','OMP_NUM_THREADS','1','--ro-bind','/usr','/usr']
    for library in ('/lib','/lib64'):
        if Path(library).exists():command+=['--ro-bind',library,library]
    command+=['--symlink','usr/bin','/bin','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/usr/share/fonts','--ro-bind',sys.prefix,sys.prefix,'--ro-bind',str(ROOT/'showcase_app'),str(ROOT/'showcase_app'),'--bind',str(tmp_path),'/out',sys.executable,'-I','-c','import sys;from pathlib import Path;sys.path.insert(0,'+repr(str(ROOT))+');from showcase_app.trailer_render import title_card;title_card(Path("/out/title.png"),"Fictional title",0)']
    result=subprocess.run(command,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr[-1000:]
    assert (tmp_path/'title.png').read_bytes().startswith(b'\x89PNG')

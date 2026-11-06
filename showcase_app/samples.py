"""Original fictional fixtures, rendered locally from source, never visitor data."""
import io
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

ROOT=Path(__file__).resolve().parents[1]
router=APIRouter()


@router.get('/api/samples/document/{name}')
async def document(name:str):
    if name not in ('operations','brief'):raise HTTPException(404)
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    source=ROOT/'examples/v3'/('operations-plan.txt' if name=='operations' else 'product-brief.txt')
    lines=source.read_text().splitlines();out=io.BytesIO();pdf=canvas.Canvas(out,pagesize=A4)
    count=10 if name=='operations' else 2
    import textwrap
    for index in range(count):
        pdf.setFont('Helvetica-Bold',17);pdf.drawString(48,790,lines[0])
        pdf.setFont('Helvetica',11);y=750
        content=f'Page {index+1} of {count}. Station S-{index+101}. Inspection quantity: {20+index}. Target date: {index+10} December 2026.\n\n'+'\n'.join(lines[2:])
        for paragraph in content.splitlines():
            for line in textwrap.wrap(paragraph,95) or ['']:
                pdf.drawString(48,y,line);y-=17
            y-=7
        pdf.setFont('Helvetica',9);pdf.drawString(48,40,'Fictional demonstration document. No real records or transactions.');pdf.showPage()
    pdf.save()
    return Response(out.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="fictional-'+name+'.pdf"'})

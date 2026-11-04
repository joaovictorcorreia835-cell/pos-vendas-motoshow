"""Relatório completo das motos com presença física confirmada."""
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from inventario_models import agora


def valor(value):
    if value is None or value == '':
        return 'Não informado'
    if isinstance(value, bool):
        return 'Sim' if value else 'Não'
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    return str(value)


def gerar_pdf(rows):
    stream=BytesIO()
    styles=getSampleStyleSheet()
    styles['BodyText'].fontSize=9
    styles['BodyText'].leading=12
    def p(text):
        return Paragraph(escape(str(text)).replace('\n','<br/>'),styles['BodyText'])
    story=[Paragraph('Motos confirmadas',styles['Title']),
           p(f'Emitido em {agora():%d/%m/%Y %H:%M} | Total: {len(rows)} moto(s)'),
           p('Motos ativas com presença física confirmada e sem saída. Demais filtros da consulta preservados.'),Spacer(1,14)]
    data=[[p(v) for v in ['Modelo','Chassi','Ano/modelo','Dias em estoque','Localiza\u00e7\u00e3o']]]
    for m in rows:
        year=f'{m.ano_fabricacao or "-"}/{m.ano_modelo or "-"}'
        data.append([p(valor(m.modelo)),p(valor(m.chassi_normalizado)),p(year),p(valor(m.dias_estoque)),p(valor(m.localizacao.nome))])
    table=Table(data,colWidths=[205,170,90,100,landscape(A4)[0]-645],repeatRows=1,hAlign='LEFT',splitInRow=1)
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce8ef')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f3f6f8')]),
        ('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#cdd7df')),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.append(table)
    if not rows:
        story.append(p('Nenhuma moto confirmada encontrada para os filtros.'))
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8)
        canvas.drawString(40,24,'Motoshow - Estoque mestre')
        canvas.drawRightString(landscape(A4)[0]-40,24,f'Página {doc.page}')
    SimpleDocTemplate(stream,pagesize=landscape(A4),rightMargin=40,leftMargin=40,topMargin=35,bottomMargin=40,
        title='Motos confirmadas',author='Motoshow').build(story,onFirstPage=footer,onLaterPages=footer)
    stream.seek(0)
    return stream

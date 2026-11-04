"""Relatório completo das motos com presença física confirmada."""
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from inventario_models import MotoEstoque, agora


LABELS = dict(id='Código', chassi='Chassi', chassi_normalizado='Chassi normalizado',
    modelo='Modelo', versao='Versão', cor='Cor', ano_modelo='Ano modelo',
    ano_fabricacao='Ano fabricação', numero_motor='Número do motor', numero_nf='Nota fiscal',
    placa='Placa', oficina_os_orcamento='OS / orçamento', oficina_observacao='Observação da oficina',
    oficina_previsao_entrega='Previsão de entrega', data_entrada='Entrada', unidade_id='Código da unidade',
    unidade_nome='Unidade', status_comercial='Status comercial', localizacao_id='Código da localização',
    localizacao_anterior='Localização anterior', presenca_confirmada='Presença confirmada',
    data_ultima_confirmacao='Última confirmação', usuario_ultima_confirmacao='Responsável pela confirmação',
    origem_dado='Origem do cadastro', observacao='Observação', ativo='Ativa',
    saida_fisica_confirmada='Saída física confirmada', data_saida_fisica='Data da saída',
    usuario_saida='Usuário da saída', destino_saida='Destino', motivo_saida='Motivo da saída',
    responsavel_saida='Responsável pela saída', entrou_pdv_em='Entrada no PDV',
    criado_em='Cadastro criado em', atualizado_em='Atualizado em', revisao='Revisão')


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
    styles['BodyText'].fontSize=8
    styles['BodyText'].leading=10
    def p(text):
        return Paragraph(escape(str(text)).replace('\n','<br/>'),styles['BodyText'])
    story=[Paragraph('Motos confirmadas',styles['Title']),
           p(f'Emitido em {agora():%d/%m/%Y %H:%M} | Total: {len(rows)} moto(s)'),
           p('Motos ativas com presença física confirmada e sem saída. Demais filtros da consulta preservados.'),Spacer(1,14)]
    for i,m in enumerate(rows,1):
        if i>1: story.append(PageBreak())
        story.append(Paragraph(escape(f'{i}. {m.modelo} - {m.chassi_normalizado}'),styles['Heading2']))
        fields=[(LABELS[c.name],getattr(m,c.name)) for c in MotoEstoque.__table__.columns]
        fields.extend([('Localização física',m.localizacao.nome),('Dias em estoque',m.dias_estoque)])
        table=Table([[p(label),p(valor(value))] for label,value in fields],colWidths=[165,350],hAlign='LEFT',splitInRow=1)
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
            ('BACKGROUND',(0,0),(0,-1),colors.HexColor('#edf3f7')),
            ('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#cdd7df')),
            ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
        story.extend([table,Spacer(1,16)])
    if not rows:
        story.append(p('Nenhuma moto confirmada encontrada para os filtros.'))
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8)
        canvas.drawString(40,24,'Motoshow - Estoque mestre')
        canvas.drawRightString(A4[0]-40,24,f'Página {doc.page}')
    SimpleDocTemplate(stream,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=35,bottomMargin=40,
        title='Motos confirmadas',author='Motoshow').build(story,onFirstPage=footer,onLaterPages=footer)
    stream.seek(0)
    return stream

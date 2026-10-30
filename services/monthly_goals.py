"""Metas declaradas e acompanhamento da planilha; sem previsão de receitas."""
from decimal import Decimal, ROUND_HALF_UP
from models import db, FaturamentoMensal
from central_models import MetaFaturamento

LABELS = {'os_centavos':'Ordem de serviço','balcao_centavos':'Venda balcão','mao_centavos':'Mão de obra'}

def plano(ano, mes, unidade):
    config=db.session.scalar(db.select(MetaFaturamento).where(MetaFaturamento.unidade==unidade,MetaFaturamento.competencia==f'{ano:04d}-{mes:02d}'))
    if not config:return None
    record=db.session.scalar(db.select(FaturamentoMensal).where(FaturamentoMensal.ano==ano,FaturamentoMensal.mes==mes,FaturamentoMensal.unidade==unidade))
    anterior_ano,anterior_mes=(ano,mes-1) if mes>1 else (ano-1,12)
    anterior=db.session.scalar(db.select(FaturamentoMensal).where(FaturamentoMensal.ano==anterior_ano,FaturamentoMensal.mes==anterior_mes,FaturamentoMensal.unidade==unidade))
    categorias=[]
    for key,label in LABELS.items():
        meta=getattr(config,key)
        realizado=sum(getattr(r,key) for r in record.linhas) if record else None
        categorias.append(dict(chave=key,nome=label,meta=meta,realizado=realizado,atingido=round(100*realizado/meta,2) if realizado is not None else None,falta=max(0,meta-realizado) if realizado is not None else None))
    total=sum(r['meta'] for r in categorias)
    realizado=sum(r['realizado'] for r in categorias) if record else None
    anterior_total=sum(r.total for r in anterior.linhas) if anterior else None
    taxa=Decimal(config.crescimento_percentual)
    proximo_ano,proximo_mes=(ano,mes+1) if mes<12 else (ano+1,1)
    return dict(unidade=unidade,competencia=config.competencia,categorias=categorias,total_meta=total,total_realizado=realizado,
        crescimento_minimo=float(taxa),crescimento_realizado=round(100*(realizado-anterior_total)/anterior_total,2) if realizado is not None and anterior_total and anterior_total>0 else None,
        proxima_competencia=f'{proximo_ano:04d}-{proximo_mes:02d}',proxima_meta=int((Decimal(total)*(1+taxa/100)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)),
        fonte='Planilha de faturamento mensal salva; não somar ao faturamento dos relatórios fiscais.',
        limite='Crescimento é objetivo gerencial, não previsão nem garantia. Comparação usa meses informados; mês em andamento é parcial.')

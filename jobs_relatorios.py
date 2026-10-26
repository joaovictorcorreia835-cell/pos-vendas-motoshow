"""Aplica uma atualização administrativa uma única vez, com backup no PostgreSQL.

O lote é transmitido exclusivamente pelo ambiente privado do Render. Relatórios
e dados pessoais não precisam ser enviados ao repositório de código.
"""
import base64
import hashlib
import json
import os
import tempfile
import zlib
from datetime import datetime
from sqlalchemy import Table,Column,MetaData,String,LargeBinary,JSON,DateTime,select,text
from models import db,Passagem,OrdemServico,VendaBalcao,FaturamentoConsultor,FaturamentoMensal,Pedido
from deployment import sqlite_snapshot

# Fora do esquema operacional: cópias portáteis não incluem backups de backups.
historico=Table('_atualizacoes_relatorios',MetaData(),
    Column('sha256',String(64),primary_key=True),
    Column('backup',LargeBinary,nullable=False),
    Column('resultado',JSON,nullable=False),
    Column('criado_em',DateTime,nullable=False))


def validar(payload):
    docs=payload['documents'];unit=payload['unit']
    if not isinstance(unit,str) or not unit.strip() or len(unit)>100 or len(docs)!=3:
        raise ValueError('Unidade ou documentos inválidos.')
    situations=[doc[1]['situacao'] for doc in docs[:2]]
    if situations not in [['Faturada','Aberta'],['Fechada','Aberta']]:
        raise ValueError('Situações de OS inválidas.')
    if situations[0]=='Fechada' and payload.get('finalizar_fechadas') is not True:
        raise ValueError('Registro de OS fechadas como finalizadas não confirmado.')
    keys=[]
    for rows,summary in docs[:2]:
        if len(rows)!=summary['count'] or not rows:raise ValueError('Contagem de OS inválida.')
        for name in ['total','pecas','servicos']:
            if sum(row[name] for row in rows)!=summary[name]:raise ValueError('Totais de OS divergentes.')
        if any(row['total']!=row['pecas']+row['servicos'] for row in rows):raise ValueError('Componentes da OS divergentes.')
        keys.extend(row['os'] for row in rows)
    if len(keys)!=len(set(keys)):raise ValueError('OS duplicadas ou com situações conflitantes.')
    rows,summary=docs[2]
    sales=[r for r in rows if r['natureza']=='Venda']
    if len(rows)!=summary['movimentos'] or len(sales)!=summary['quantidades']['Venda'] or sum(r['liquido'] for r in sales)!=summary['vendas']:
        raise ValueError('Totais de vendas divergentes.')
    if not sales or len({r['nota'] for r in sales})!=len(sales):raise ValueError('Notas ausentes ou duplicadas.')
    start=datetime.fromisoformat(payload['sales_start']);end=datetime.fromisoformat(payload['sales_end_exclusive'])
    if not start<end or (end-start).days>366:raise ValueError('Período de balcão inválido.')
    if any(not start<=datetime.fromisoformat(r['data'])<end for r in sales):raise ValueError('Venda fora do período autorizado.')
    if payload.get('delete_absent') is not True:raise ValueError('Exclusão de ausentes não autorizada no lote.')
    return docs,unit,start,end,set(keys),sales


def aplicar_lote(payload,digest):
    docs,unit,start,end,allowed,sales=validar(payload)
    historico.create(db.engine,checkfirst=True)
    with db.engine.connect() as guard:
        postgres=db.engine.dialect.name=='postgresql'
        if postgres:
            guard.execute(text('SELECT pg_advisory_lock(5570760608852037463)'));guard.commit()
        try:
            old=guard.execute(select(historico.c.resultado).where(historico.c.sha256==digest)).scalar()
            guard.commit()
            if old is not None:return dict(old,reaplicado=False)
            # Bloqueia gravações durante a cópia e a conciliação; leituras continuam.
            if postgres:
                names=', '.join('"'+table.name+'"' for table in db.metadata.sorted_tables)
                db.session.execute(text('LOCK TABLE '+names+' IN SHARE ROW EXCLUSIVE MODE'))
            manual_before=[tuple(row) for row in db.session.execute(select(FaturamentoConsultor.__table__).order_by(FaturamentoConsultor.id))]
            months_before=[tuple(row) for row in db.session.execute(select(FaturamentoMensal.__table__).order_by(FaturamentoMensal.id))]
            orders_before=[tuple(row) for row in db.session.execute(select(Pedido.__table__).order_by(Pedido.id))]
            backup=sqlite_snapshot(db.engine).getvalue()
            from atualizar_relatorios import synchronize
            # A data de entrada/saída da OS não é a data fiscal. O relatório
            # mensal informa a competência; não inventamos um dia de emissão.
            if (end.replace(day=1)-start.replace(day=1)).days<32 and start.day==1 and (end.month==start.month or end.day==1):
                docs[0][1]['competencia_faturamento']=start.strftime('%Y-%m')
            with tempfile.TemporaryDirectory() as folder:
                plan=synchronize(docs,unit,folder,apply=True,backup_dir=folder,commit=False,criar_backup=False)
            absent=db.session.scalars(select(OrdemServico).join(Passagem).where(Passagem.unidade==unit,OrdemServico.numero.not_in(allowed))).all()
            removed_os=[o.numero for o in absent]
            for order in absent:db.session.delete(order.passagem)
            notes={r['nota'] for r in sales}
            candidates=db.session.scalars(select(VendaBalcao).join(Passagem).where(VendaBalcao.unidade==unit,Passagem.data>=start,Passagem.data<end)).all()
            removed_sales=[]
            for sale in candidates:
                if sale.natureza!='Venda' or sale.nota not in notes:
                    removed_sales.append(sale.nota);db.session.delete(sale.passagem)
            db.session.flush()
            final_os=db.session.scalars(select(OrdemServico).join(Passagem).where(Passagem.unidade==unit)).all()
            if {o.numero for o in final_os}!=allowed:raise ValueError('Conciliação de OS divergente.')
            for rows,summary in docs[:2]:
                expected={r['os']:r for r in rows}
                status='Aberta' if summary['situacao']=='Aberta' else 'Finalizada'
                for order in final_os:
                    if order.numero in expected:
                        row=expected[order.numero];p=order.passagem
                        if p.status!=status or p.total!=row['total']:raise ValueError('Situação ou valor da OS divergente.')
            final_sales=db.session.scalars(select(VendaBalcao).join(Passagem).where(VendaBalcao.unidade==unit,Passagem.data>=start,Passagem.data<end)).all()
            if {v.nota for v in final_sales}!=notes or any(v.natureza!='Venda' for v in final_sales):raise ValueError('Conciliação de balcão divergente.')
            if sum(v.passagem.total for v in final_sales)!=docs[2][1]['vendas']:raise ValueError('Valor de balcão divergente.')
            if manual_before!=[tuple(row) for row in db.session.execute(select(FaturamentoConsultor.__table__).order_by(FaturamentoConsultor.id))]:raise ValueError('Faturamento manual alterado.')
            if months_before!=[tuple(row) for row in db.session.execute(select(FaturamentoMensal.__table__).order_by(FaturamentoMensal.id))]:raise ValueError('Meses manuais alterados.')
            if orders_before!=[tuple(row) for row in db.session.execute(select(Pedido.__table__).order_by(Pedido.id))]:raise ValueError('Pedidos alterados.')
            result=dict(situacao_relatorio=docs[0][1]['situacao'],os_finalizadas_relatorio=docs[0][1]['count'],os_faturadas=docs[0][1]['count'] if docs[0][1]['situacao']=='Faturada' else 0,os_abertas=docs[1][1]['count'],os_novas=len(plan['os_novas']),os_excluidas=len(removed_os),os_finalizadas=len(plan['os_finalizadas']),vendas=len(sales),vendas_novas=len(plan['vendas_novas']),vendas_excluidas=len(removed_sales),devolucoes_ignoradas=plan['devolucoes_ignoradas'],faturadas_centavos=docs[0][1]['total'],abertas_centavos=docs[1][1]['total'],balcao_centavos=docs[2][1]['vendas'],backup_sha256=hashlib.sha256(backup).hexdigest())
            db.session.execute(historico.insert().values(sha256=digest,backup=backup,resultado=result,criado_em=datetime.now()))
            db.session.commit()
            return dict(result,reaplicado=True)
        except Exception:
            db.session.rollback();raise
        finally:
            if postgres:
                guard.execute(text('SELECT pg_advisory_unlock(5570760608852037463)'));guard.commit()


def executar_pendente():
    packed=os.environ.get('RELATORIOS_BATCH_GZ','')
    if not packed:return
    try:
        inflater=zlib.decompressobj()
        raw=inflater.decompress(base64.b64decode(packed,validate=True),5*1024*1024)
        if inflater.unconsumed_tail or not inflater.eof:raise ValueError('Lote inválido ou muito grande.')
        payload=json.loads(raw)
        digest=hashlib.sha256(raw).hexdigest()
        if payload.get('kind')=='mensal':
            from jobs_mensais import aplicar_meses
            result=aplicar_meses(payload,digest)
        elif payload.get('kind')=='pedidos':
            from jobs_pedidos import aplicar_pedidos
            result=aplicar_pedidos(payload,digest)
        elif payload.get('kind')=='usuario_estoque':
            from jobs_usuarios import aplicar_usuario_estoque
            result=aplicar_usuario_estoque(payload,digest)
        elif payload.get('kind')=='usuario_admin':
            from jobs_usuarios import aplicar_usuario_admin
            result=aplicar_usuario_admin(payload,digest)
        else:
            result=aplicar_lote(payload,digest)
        print('RELATORIOS_JOB_OK '+json.dumps(dict(lote=digest,**result)),flush=True)
    except Exception as error:
        print('RELATORIOS_JOB_ERRO '+type(error).__name__,flush=True)
        raise RuntimeError('Atualização administrativa recusada; nenhuma alteração parcial foi mantida.') from None

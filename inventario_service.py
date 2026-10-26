"""Regras transacionais do estoque, inventários, movimentações e auditoria."""
import hashlib
import json
import re
import secrets
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import g, has_request_context, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from inventario_models import *

COMERCIAIS = ('DISPONÍVEL', 'RESERVADA', 'AGUARDANDO APROVAÇÃO', 'FATURADA', 'VENDIDA', 'TRANSFERÊNCIA', 'DEMONSTRAÇÃO', 'OUTRO')
PADRAO_LOCAIS = [('PATIO','PÁTIO',True),('GALPAO','GALPÃO',True),('PDV','PDV / SALÃO',True),('PDV_CIDADE_JARDIM','PDV CIDADE JARDIM',True),('PDV_NOVO_HORIZONTE','PDV NOVO HORIZONTE',True),('OFICINA','OFICINA',True),('ENTREGA','ENTREGA',True),('TRANSITO','TRÂNSITO',False),('OUTRA_UNIDADE','OUTRA UNIDADE',False),('NAO_LOCALIZADA','NÃO LOCALIZADA',False),('A_CONFIRMAR','A CONFIRMAR',False)]
RANK = {'CONSULTA':0, 'OPERADOR':1, 'GESTOR':2, 'ADMIN':3}
RANK['ESTOQUE_MOTOS']=1


def status_fonte(value):
    value=str(value or '').lower()
    for fragment,status in [('aprova','AGUARDANDO APROVAÇÃO'),('reserv','RESERVADA'),('fatur','FATURADA'),('vendid','VENDIDA'),('transfer','TRANSFERÊNCIA'),('demonstr','DEMONSTRAÇÃO'),('dispon','DISPONÍVEL')]:
        if fragment in value:return status
    return 'OUTRO'


def normalizar_chassi(value):
    return chassi_canonico(value)


def ator():
    user = getattr(g, 'usuario', None) if has_request_context() else None
    return (user.id, user.login) if user else (None, 'Sistema / migração')


def papel(user=None):
    user = user or (getattr(g, 'usuario', None) if has_request_context() else None)
    if not user:
        return 'CONSULTA'
    if user.administrador:
        return 'ADMIN'
    if user.estoque_exclusivo:
        return 'ESTOQUE_MOTOS'
    row = db.session.get(PapelEstoque, user.id)
    return row.papel if row else user.perfil if user.perfil in ('GESTOR','ADMIN') else 'OPERADOR'


def permitir(minimo):
    from flask import abort
    if RANK[papel()] < RANK[minimo]:
        abort(403, description='Seu perfil não permite esta ação no estoque.')


def unidade(nome):
    nome = (nome or '').strip()
    if not nome or len(nome) > 150:
        raise ValueError('Informe uma unidade válida.')
    row = db.session.scalar(select(UnidadeEstoque).where(UnidadeEstoque.nome == nome))
    if row is None:
        row = UnidadeEstoque(nome=nome)
        db.session.add(row); db.session.flush()
    return row


def local(ident):
    row = db.session.get(LocalEstoque, int(ident)) if str(ident).isdigit() else db.session.scalar(select(LocalEstoque).where(LocalEstoque.codigo == ident))
    if row is None or not row.ativo:
        raise ValueError('Localização inválida ou inativa.')
    return row


def defaults():
    for code, name, physical in PADRAO_LOCAIS:
        if not db.session.scalar(select(LocalEstoque.id).where(LocalEstoque.codigo == code)):
            db.session.add(LocalEstoque(codigo=code, nome=name, grupo='PDV' if code.startswith('PDV_') else code, fisica=physical))
    # Retira das novas operações sem apagar referências e auditorias anteriores.
    for retired in db.session.scalars(select(LocalEstoque).where(LocalEstoque.grupo=='LAVAGEM')):
        retired.ativo=False
    if db.session.get(PoliticaEstoque, 1) is None:
        db.session.add(PoliticaEstoque(id=1))
    db.session.flush()
    from models import Configuracao
    config=db.session.get(Configuracao,1)
    if config:
        unidade(config.unidade)


def estado(m):
    return dict(chassi=m.chassi_normalizado, modelo=m.modelo, cor=m.cor, unidade=m.unidade_nome,
        unidade_id=m.unidade_id, localizacao=m.localizacao.nome, localizacao_id=m.localizacao_id,
        grupo=m.localizacao.grupo, status=m.status_comercial, presenca=m.presenca_confirmada,
        saida=m.saida_fisica_confirmada, ativo=m.ativo, revisao=m.revisao, versao=m.versao,
        ano_modelo=m.ano_modelo,ano_fabricacao=m.ano_fabricacao,numero_motor=m.numero_motor,numero_nf=m.numero_nf,
        data_entrada=m.data_entrada.isoformat() if m.data_entrada else None,
        ultima_confirmacao=m.data_ultima_confirmacao.isoformat() if m.data_ultima_confirmacao else None,
        usuario_confirmacao=m.usuario_ultima_confirmacao,origem=m.origem_dado,observacao=m.observacao,
        data_saida=m.data_saida_fisica.isoformat() if m.data_saida_fisica else None,usuario_saida=m.usuario_saida,
        destino_saida=m.destino_saida,motivo_saida=m.motivo_saida,responsavel_saida=m.responsavel_saida)


def auditar(m, tipo, anterior=None, observacao='', inventario_id=None, novo=None, chassi=None):
    uid, name = ator()
    row = MovimentacaoMoto(moto_id=m.id if m else None, chassi=m.chassi_normalizado if m else chassi or '',
        tipo_movimentacao=tipo, usuario_id=uid, usuario_nome=name, anterior=anterior or {},
        novo=novo if novo is not None else estado(m) if m else {}, observacao=observacao,
        inventario_id=inventario_id, ip=request.remote_addr or '' if has_request_context() else '')
    row.unidade_origem = row.anterior.get('unidade',''); row.unidade_destino = row.novo.get('unidade','')
    row.localizacao_origem = row.anterior.get('localizacao',''); row.localizacao_destino = row.novo.get('localizacao','')
    db.session.add(row)
    return row


def obter_moto(ident, revisao=None):
    m = db.session.scalar(select(MotoEstoque).where(MotoEstoque.id == ident).with_for_update())
    if not m:
        raise ValueError('Moto não cadastrada.')
    from estoque_acesso import verificar_moto
    verificar_moto(m)
    if revisao is not None and int(revisao) != m.revisao:
        raise ValueError('Esta moto foi alterada por outro usuário. Atualize a página.')
    return m


def cadastrar(data, origem='Cadastro manual'):
    vin = normalizar_chassi(data.get('chassi'))
    existing=db.session.scalar(select(MotoEstoque).where(MotoEstoque.chassi_normalizado==vin).with_for_update())
    archived=existing and not existing.ativo and not existing.saida_fisica_confirmada
    if existing and not archived:
        raise ValueError('Chassi já cadastrado no estoque mestre.')
    if archived:
        from estoque_acesso import verificar_moto
        verificar_moto(existing)
    model = data.get('modelo','').strip()
    if not model or len(model) > 200:
        raise ValueError('Informe o modelo (até 200 caracteres).')
    unit = unidade(data.get('unidade'))
    status = data.get('status_comercial') or 'DISPONÍVEL'
    if status not in COMERCIAIS:
        raise ValueError('Status comercial inválido.')
    before=estado(existing) if archived else None
    m=existing if archived else MotoEstoque(chassi=vin,chassi_normalizado=vin)
    m.modelo=model;m.unidade_id=unit.id;m.unidade_nome=unit.nome
    m.status_comercial=status;m.localizacao=local('A_CONFIRMAR');m.origem_dado=origem
    m.ativo=True;m.presenca_confirmada=False
    for key, size in [('cor',100),('versao',100),('ano_modelo',4),('ano_fabricacao',4),('numero_motor',100),('numero_nf',80),('placa',30),('observacao',10000)]:
        value = data.get(key,'') or ''
        if len(value) > size:
            raise ValueError('Campo muito longo: ' + key)
        setattr(m,key,value)
    if data.get('data_entrada'):
        m.data_entrada = date.fromisoformat(str(data['data_entrada']))
        if m.data_entrada > agora().date():
            raise ValueError('A data de entrada não pode estar no futuro.')
    db.session.add(m); db.session.flush()
    auditar(m,'RECADASTRO' if archived else 'ENTRADA',before,observacao=origem)
    return m


def pendente_transferencia(m):
    return db.session.scalar(select(TransferenciaMoto).where(TransferenciaMoto.pendente_moto == m.id))


def mover(m, destino, observacao='', tipo='ALTERAÇÃO DE LOCALIZAÇÃO', inventario_id=None, recebimento=False):
    from estoque_acesso import verificar_moto
    verificar_moto(m)
    if m.saida_fisica_confirmada or not m.ativo:
        raise ValueError('Confirme o retorno antes de movimentar uma moto que saiu.')
    if pendente_transferencia(m) and not recebimento:
        raise ValueError('Esta moto está em transferência. Use Confirmar recebimento.')
    before = estado(m); target = local(destino)
    m.localizacao_anterior = m.localizacao.nome
    if target.grupo == 'PDV' and m.localizacao.grupo != 'PDV':
        m.entrou_pdv_em = agora()
    if target.grupo != 'PDV':
        m.entrou_pdv_em = None
    m.localizacao = target
    m.presenca_confirmada = target.fisica
    m.data_ultima_confirmacao = agora(); m.usuario_ultima_confirmacao = ator()[1]
    m.atualizado_em = agora()
    db.session.flush()
    auditar(m,tipo,before,observacao,inventario_id)
    if target.grupo=='NAO_LOCALIZADA' and inventario_id is None:
        if not db.session.scalar(select(DivergenciaMoto.id).where(DivergenciaMoto.moto_id==m.id,DivergenciaMoto.tipo=='NÃO ENCONTRADA',DivergenciaMoto.resolvido.is_(False))):
            db.session.add(DivergenciaMoto(moto_id=m.id,chassi=m.chassi_normalizado,tipo='NÃO ENCONTRADA',esperado=before['localizacao'],encontrado=target.nome,responsavel=ator()[1]))


def saida(m, destino, motivo, responsavel, observacao='', entrega_cliente=False):
    from estoque_acesso import verificar_moto
    verificar_moto(m)
    if not all(str(v or '').strip() for v in (destino,motivo,responsavel)):
        raise ValueError('Informe destino, motivo e responsável pela saída física.')
    if len(destino)>200 or len(motivo)>200 or len(responsavel)>150:
        raise ValueError('Destino/motivo: até 200 caracteres; responsável: até 150.')
    if m.saida_fisica_confirmada or pendente_transferencia(m):
        raise ValueError('Moto já saiu ou possui transferência pendente.')
    before = estado(m)
    m.saida_fisica_confirmada=True; m.presenca_confirmada=False; m.ativo=False
    m.data_saida_fisica=agora(); m.usuario_saida=ator()[1]
    m.destino_saida=destino; m.motivo_saida=motivo; m.responsavel_saida=responsavel
    m.atualizado_em=agora()
    db.session.flush(); auditar(m,'SAÍDA',before,observacao,novo=dict(estado(m),destino=destino,motivo=motivo,responsavel=responsavel,entrega_cliente=bool(entrega_cliente)))


def entregas_periodo(inicio,fim,unidade_nome=''):
    from estoque_acesso import exclusivo,unidade_usuario
    query=select(MovimentacaoMoto).where(MovimentacaoMoto.tipo_movimentacao=='SAÍDA',MovimentacaoMoto.data_hora>=datetime.combine(inicio,datetime.min.time()),MovimentacaoMoto.data_hora<datetime.combine(fim+timedelta(days=1),datetime.min.time()))
    if exclusivo():query=query.where(MovimentacaoMoto.unidade_origem==unidade_usuario().nome)
    if unidade_nome:query=query.where(MovimentacaoMoto.unidade_origem==unidade_nome)
    return [e for e in db.session.scalars(query.order_by(MovimentacaoMoto.data_hora.desc(),MovimentacaoMoto.id.desc())) if e.novo.get('entrega_cliente') is True]


def retorno(m, destino, motivo):
    if not m.saida_fisica_confirmada or not motivo.strip():
        raise ValueError('O retorno exige uma saída anterior e uma justificativa.')
    before=estado(m); m.saida_fisica_confirmada=False; m.ativo=True
    # Datas da saída anterior permanecem na ficha e na auditoria.
    mover(m,destino,motivo,'RETORNO')
    auditar(m,'CANCELAMENTO DE SAÍDA',before,motivo)


def transferir(m, destino, observacao):
    unit=db.session.get(UnidadeEstoque,int(destino))
    if not unit or not unit.ativo or unit.id==m.unidade_id or m.saida_fisica_confirmada or pendente_transferencia(m):
        raise ValueError('Informe uma unidade de destino diferente e uma moto sem transferência pendente.')
    mover(m,'TRANSITO',observacao,'TRANSFERÊNCIA')
    row=TransferenciaMoto(moto_id=m.id,pendente_moto=m.id,unidade_origem_id=m.unidade_id,
        unidade_destino_id=unit.id,iniciada_por=ator()[1],observacao=observacao)
    db.session.add(row); db.session.flush()
    auditar(m,'DESTINO DE TRANSFERÊNCIA',observacao=observacao,novo=dict(estado(m),destino=unit.nome,transferencia_id=row.id))
    return row


def receber(m, destino, observacao):
    transfer=pendente_transferencia(m)
    if not transfer:
        raise ValueError('Não há transferência pendente.')
    from estoque_acesso import verificar_unidade
    verificar_unidade(transfer.unidade_destino_id)
    target=local(destino)
    if not target.fisica:
        raise ValueError('Selecione o local físico do recebimento.')
    unit=db.session.get(UnidadeEstoque,transfer.unidade_destino_id)
    before=estado(m); m.unidade_id=unit.id; m.unidade_nome=unit.nome
    mover(m,target.id,observacao,'RECEBIMENTO',recebimento=True)
    transfer.recebida_em=agora(); transfer.recebida_por=ator()[1]; transfer.pendente_moto=None
    auditar(m,'TRANSFERÊNCIA RECEBIDA',before,observacao)


def abrir_inventario(unidade_id,nome,primeiro=False,incluir_transito=True):
    from estoque_acesso import verificar_unidade
    verificar_unidade(int(unidade_id))
    unit=db.session.get(UnidadeEstoque,int(unidade_id))
    if not unit or not unit.ativo or not nome.strip():
        raise ValueError('Selecione a unidade e dê um nome ao inventário.')
    # O bloqueio da unidade serializa abertura de inventários concorrentes.
    db.session.execute(select(UnidadeEstoque.id).where(UnidadeEstoque.id==unit.id).with_for_update()).scalar()
    if db.session.scalar(select(InventarioMoto.id).where(InventarioMoto.unidade_id==unit.id,InventarioMoto.status.not_in(['CONCLUÍDO','CANCELADO']))):
        raise ValueError('Já existe inventário aberto nesta unidade.')
    query=select(MotoEstoque).where(MotoEstoque.unidade_id==unit.id,MotoEstoque.ativo.is_(True),MotoEstoque.saida_fisica_confirmada.is_(False))
    if not incluir_transito:
        query=query.where(MotoEstoque.localizacao_id.not_in(select(LocalEstoque.id).where(LocalEstoque.grupo.in_(['TRANSITO','OUTRA_UNIDADE']))))
    rows=db.session.scalars(query.order_by(MotoEstoque.id).with_for_update()).all()
    inv=InventarioMoto(codigo='INV-'+agora().strftime('%Y%m%d')+'-'+secrets.token_hex(4).upper(),nome=nome.strip()[:200],
        unidade_id=unit.id,unidade_aberta_id=unit.id,unidade_nome=unit.nome,iniciado_por=ator()[1],total_esperado=len(rows),observacao=('Primeiro inventário geral. ' if primeiro else '')+('Escopo: toda a responsabilidade da unidade.' if incluir_transito else 'Escopo: unidade física, excluindo trânsito e outra unidade confirmados.'))
    db.session.add(inv); db.session.flush()
    for m in rows:
        db.session.add(InventarioMotoItem(inventario_id=inv.id,moto_id=m.id,chassi=m.chassi_normalizado,
            esperado=True,snapshot=dict(estado(m),cor=m.cor,ano_modelo=m.ano_modelo),localizacao_esperada=m.localizacao.nome))
    auditar(None,'ABERTURA DE INVENTÁRIO',inventario_id=inv.id,novo=dict(codigo=inv.codigo,esperadas=len(rows),unidade=unit.nome,escopo=inv.observacao))
    return inv


def inventario_aberto(ident):
    inv=db.session.scalar(select(InventarioMoto).where(InventarioMoto.id==ident).with_for_update())
    if not inv or inv.status in ('CONCLUÍDO','CANCELADO'):
        raise ValueError('Inventário inexistente ou encerrado. O resultado final é imutável.')
    from estoque_acesso import verificar_unidade
    verificar_unidade(inv.unidade_id)
    return inv


def divergir(item,tipo,esperado='',encontrado=''):
    row=db.session.scalar(select(DivergenciaMoto).where(DivergenciaMoto.item_id==item.id,DivergenciaMoto.tipo==tipo))
    if row is None:
        row=DivergenciaMoto(item_id=item.id,inventario_id=item.inventario_id,moto_id=item.moto_id,chassi=item.chassi,
            tipo=tipo,esperado=esperado,encontrado=encontrado,responsavel=ator()[1])
        db.session.add(row)
    item.divergencia=True
    if tipo not in (item.tipo_divergencia or ''):
        item.tipo_divergencia=((item.tipo_divergencia or '')+' / '+tipo).strip(' /')
    return row


def resumo_inventario(inv):
    if inv.resultado_final:
        return inv.resultado_final
    items=db.session.scalars(select(InventarioMotoItem).where(InventarioMotoItem.inventario_id==inv.id)).all()
    differences=db.session.scalars(select(DivergenciaMoto).where(DivergenciaMoto.inventario_id==inv.id)).all()
    pending={d.item_id for d in differences if not d.resolvido}
    expected=[i for i in items if i.esperado]
    reconciled=sum(i.encontrado and i.id not in pending for i in expected)
    percentage=round(reconciled*100/inv.total_esperado,2) if inv.total_esperado else 0
    return dict(esperadas=inv.total_esperado,encontradas=sum(i.encontrado and i.esperado for i in items),
        nao_encontradas=sum(not i.encontrado for i in expected),extras=sum(i.encontrado and not i.esperado for i in items),
        extras_sem_cadastro=sum(i.encontrado and not i.esperado and i.moto_id is None for i in items),
        localizacao_divergente=sum(d.tipo=='LOCALIZAÇÃO DIVERGENTE' for d in differences),pendentes=sum(not d.resolvido for d in differences),
        conciliacao=percentage,sem_divergencia=reconciled,status='SEM BASE' if not inv.total_esperado else 'CONCILIADO' if percentage==100 else 'ATENÇÃO' if percentage>=95 else 'DIVERGENTE')


def conferir(inv,vin,destino,corrigir=False,observacao='',cadastro=None):
    from estoque_acesso import verificar_unidade, verificar_moto
    verificar_unidade(inv.unidade_id)
    if inv.status in ('CONCLUÍDO','CANCELADO'):
        raise ValueError('Inventário encerrado não permite conferência ou cadastro.')
    vin=normalizar_chassi(vin); target=local(destino)
    item=db.session.scalar(select(InventarioMotoItem).where(InventarioMotoItem.inventario_id==inv.id,InventarioMotoItem.chassi==vin).with_for_update())
    m=db.session.scalar(select(MotoEstoque).where(MotoEstoque.chassi_normalizado==vin).with_for_update())
    verificar_moto(m)
    if item is None and m:
        item=db.session.scalar(select(InventarioMotoItem).where(InventarioMotoItem.inventario_id==inv.id,InventarioMotoItem.moto_id==m.id).with_for_update())
    completar=m is None and cadastro is not None
    if item and item.encontrado and not corrigir and not completar:
        return dict(duplicada=True,item=item)
    if corrigir and (not observacao.strip() or papel() not in ('ADMIN','GESTOR')):
        raise ValueError('Correção exige gestor e justificativa.')
    if item is None:
        item=InventarioMotoItem(inventario_id=inv.id,chassi=vin,moto_id=m.id if m else None,esperado=False,
            snapshot=estado(m) if m else dict(modelo='Não cadastrada',unidade='Não prevista'),localizacao_esperada=m.localizacao.nome if m else 'Não prevista')
        db.session.add(item); db.session.flush()
    cadastrada=False
    if completar:
        modelo=str(cadastro.get('modelo','')).strip()
        cor=str(cadastro.get('cor','')).strip()
        entrada=str(cadastro.get('data_entrada','')).strip()
        if not modelo or not cor or not entrada:
            raise ValueError('Para cadastrar esta moto, informe modelo, cor e data de entrada.')
        if len(modelo)>200 or len(cor)>100:
            raise ValueError('Modelo: até 200 caracteres; cor: até 100 caracteres.')
        try:date.fromisoformat(entrada)
        except ValueError:raise ValueError('Informe uma data de entrada válida.') from None
        unit=db.session.get(UnidadeEstoque,inv.unidade_id)
        if not unit or not unit.ativo:
            raise ValueError('A unidade do inventário precisa estar ativa para cadastrar a moto.')
        m=cadastrar(dict(chassi=vin,modelo=modelo,cor=cor,data_entrada=entrada,unidade=unit.nome),
            'Cadastro durante inventário '+inv.codigo)
        item.moto_id=m.id;cadastrada=True
    previous=dict(localizacao=item.localizacao_encontrada,encontrado=item.encontrado,conferido_por=item.conferido_por)
    item.encontrado=True; item.localizacao_encontrada=target.nome; item.conferido_em=agora(); item.conferido_por=ator()[1]
    if not item.esperado:
        divergir(item,'EXTRA','Não prevista',target.nome)
    if m and item.snapshot.get('unidade_id',m.unidade_id)!=inv.unidade_id:
        divergir(item,'UNIDADE DIVERGENTE',item.snapshot.get('unidade',''),inv.unidade_nome)
    expected_group=item.snapshot.get('grupo','A_CONFIRMAR')
    if item.esperado and expected_group!='A_CONFIRMAR' and item.localizacao_esperada!=target.nome:
        divergir(item,'LOCALIZAÇÃO DIVERGENTE',item.localizacao_esperada,target.nome)
    if (expected_group=='TRANSITO' or (m and m.localizacao.grupo=='TRANSITO')) and target.fisica:
        divergir(item,'STATUS INCOMPATÍVEL','TRÂNSITO',target.nome)
    if m and m.saida_fisica_confirmada:
        divergir(item,'STATUS INCOMPATÍVEL','Saída física confirmada',target.nome)
    # Contagem em outra unidade/saída/transferência exige conciliação explícita.
    if m and m.unidade_id==inv.unidade_id and not m.saida_fisica_confirmada and not pendente_transferencia(m):
        mover(m,target.id,observacao,'INVENTÁRIO',inv.id)
    else:
        auditar(m,'INVENTÁRIO / EXTRA',previous,observacao,inv.id,novo=dict(localizacao=target.nome,encontrado=True),chassi=vin)
    if inv.status=='ABERTO':
        inv.status='EM CONFERÊNCIA'
    if cadastrada:
        justification='Cadastro completado durante a conferência: modelo, cor e data de entrada informados.'
        for d in db.session.scalars(select(DivergenciaMoto).where(DivergenciaMoto.item_id==item.id,DivergenciaMoto.tipo=='EXTRA')):
            d.moto_id=m.id
            if not d.resolvido:
                d.resolvido=True;d.justificativa=justification;d.resolvido_por=ator()[1];d.resolvido_em=agora()
        item.justificativa=justification;item.resolvido_por=ator()[1];item.resolvido_em=agora()
        db.session.flush()
        item.resolvido=not db.session.scalar(select(DivergenciaMoto.id).where(DivergenciaMoto.item_id==item.id,DivergenciaMoto.resolvido.is_(False)))
        auditar(m,'CADASTRO NA CONFERÊNCIA',dict(cadastrada=False),justification,inv.id)
    for d in db.session.scalars(select(DivergenciaMoto).where(DivergenciaMoto.item_id==item.id,DivergenciaMoto.resolvido.is_(False))):
        if d.tipo in ('NÃO ENCONTRADA','SAÍDA NÃO CONFIRMADA'):
            d.resolvido=True; d.justificativa='Moto localizada em nova conferência'; d.resolvido_por=ator()[1]; d.resolvido_em=agora()
    db.session.flush()
    return dict(duplicada=False,item=item,cadastrada=cadastrada)


def analisar(inv):
    for item in db.session.scalars(select(InventarioMotoItem).where(InventarioMotoItem.inventario_id==inv.id,InventarioMotoItem.esperado.is_(True),InventarioMotoItem.encontrado.is_(False))):
        divergir(item,'NÃO ENCONTRADA',item.localizacao_esperada,'Não localizada na contagem')
        if item.snapshot.get('status') in ('VENDIDA','FATURADA') and not item.snapshot.get('saida'):
            divergir(item,'SAÍDA NÃO CONFIRMADA',item.snapshot['status'],'Saída física não registrada')
        m=obter_moto(item.moto_id) if item.moto_id else None
        if m and not m.saida_fisica_confirmada and m.localizacao.grupo not in ('TRANSITO','NAO_LOCALIZADA') and not pendente_transferencia(m):
            mover(m,'NAO_LOCALIZADA','Não encontrada na análise do inventário; nenhuma saída foi presumida.','INVENTÁRIO / NÃO LOCALIZADA',inv.id)
    inv.status='AGUARDANDO CONCILIAÇÃO'; db.session.flush()
    return resumo_inventario(inv)


def resolver(d,justificativa,acao='JUSTIFICAR',destino=None,dados=None):
    if not justificativa.strip():
        raise ValueError('Toda resolução exige justificativa.')
    if d.inventario_id:
        inventario_aberto(d.inventario_id)
    if d.resolvido:
        raise ValueError('Divergência já resolvida.')
    m=obter_moto(d.moto_id) if d.moto_id else None
    before=dict(resolvido=False,tipo=d.tipo)
    if acao=='CORRIGIR LOCALIZAÇÃO':
        if not m:
            raise ValueError('Cadastre ou vincule a moto primeiro.')
        mover(m,destino,justificativa,'CORREÇÃO')
    elif acao=='CONFIRMAR SAÍDA':
        if not m:
            raise ValueError('Moto não cadastrada.')
        saida(m,dados.get('destino',''),dados.get('motivo',''),dados.get('responsavel',''),justificativa)
    elif acao=='CADASTRAR MOTO':
        if m:
            raise ValueError('Esta moto já está cadastrada.')
        fields=dict(dados,chassi=d.chassi)
        if d.inventario_id:
            inv=db.session.get(InventarioMoto,d.inventario_id)
            if fields.get('unidade') and fields['unidade']!=inv.unidade_nome:
                raise ValueError('Cadastre a extra na unidade onde o inventário a encontrou: '+inv.unidade_nome)
            fields['unidade']=inv.unidade_nome
        m=cadastrar(fields,'Extra de inventário')
        d.moto_id=m.id
        if d.item_id:
            item=db.session.get(InventarioMotoItem,d.item_id); item.moto_id=m.id
        mover(m,destino,justificativa,'CORREÇÃO',d.inventario_id)
    elif acao=='VINCULAR CADASTRO':
        if dados.get('chassi_cadastro'):
            code=normalizar_chassi(dados['chassi_cadastro'])
            m=db.session.scalar(select(MotoEstoque).where(MotoEstoque.chassi_normalizado==code).with_for_update())
            if not m:raise ValueError('Chassi do cadastro a vincular não encontrado.')
        else:
            m=obter_moto(int(dados['moto_id']))
        if d.item_id:
            item=db.session.get(InventarioMotoItem,d.item_id)
            other=db.session.scalar(select(InventarioMotoItem.id).where(InventarioMotoItem.inventario_id==item.inventario_id,InventarioMotoItem.moto_id==m.id,InventarioMotoItem.id!=item.id))
            if other:
                raise ValueError('Esta moto já tem item no inventário. Justifique o erro sem duplicar a contagem.')
            item.moto_id=m.id
        d.moto_id=m.id
    elif acao=='CONFIRMAR TRANSFERÊNCIA':
        if not m:
            raise ValueError('Moto não cadastrada.')
        receber(m,destino,justificativa)
    elif acao not in ('JUSTIFICAR','MARCAR COMO RESOLVIDO'):
        raise ValueError('Ação de resolução inválida.')
    d.resolvido=True; d.justificativa=justificativa; d.resolvido_em=agora(); d.resolvido_por=ator()[1]
    if d.item_id:
        item=db.session.get(InventarioMotoItem,d.item_id)
        item.justificativa=justificativa; item.resolvido_em=agora(); item.resolvido_por=ator()[1]
        db.session.flush()
        item.resolvido=not db.session.scalar(select(DivergenciaMoto.id).where(DivergenciaMoto.item_id==item.id,DivergenciaMoto.resolvido.is_(False)))
    auditar(m,'RESOLUÇÃO DE DIVERGÊNCIA',before,justificativa,d.inventario_id,novo=dict(resolvido=True,acao=acao,divergencia_id=d.id),chassi=d.chassi)


def encerrar(inv,observacao='',cancelar=False):
    if cancelar and not observacao.strip():
        raise ValueError('Informe o motivo do cancelamento.')
    if not cancelar:
        result=analisar(inv)
        if result['pendentes']:
            raise ValueError('Resolva ou justifique todas as divergências antes de encerrar.')
    else:
        for d in db.session.scalars(select(DivergenciaMoto).where(DivergenciaMoto.inventario_id==inv.id,DivergenciaMoto.resolvido.is_(False))).all():
            resolver(d,'Inventário cancelado: '+observacao,'JUSTIFICAR')
        result=resumo_inventario(inv)
    db.session.flush()
    inv.resultado_final=dict(result,escopo=inv.observacao,itens=[dict(chassi=i.chassi,esperado=i.esperado,snapshot=i.snapshot,encontrado=i.encontrado,localizacao=i.localizacao_encontrada,conferido_em=str(i.conferido_em or ''),conferido_por=i.conferido_por,justificativa=i.justificativa) for i in db.session.scalars(select(InventarioMotoItem).where(InventarioMotoItem.inventario_id==inv.id))],
        divergencias=[dict(tipo=d.tipo,chassi=d.chassi,resolvido=d.resolvido,justificativa=d.justificativa) for d in db.session.scalars(select(DivergenciaMoto).where(DivergenciaMoto.inventario_id==inv.id))])
    inv.total_encontrado=result['encontradas']; inv.total_nao_encontrado=result['nao_encontradas']; inv.total_extra=result['extras']
    inv.total_localizacao_divergente=result['localizacao_divergente']; inv.percentual_conciliacao=result['conciliacao']
    inv.encerrado_em=agora(); inv.encerrado_por=ator()[1]; inv.observacao=(inv.observacao+'\nEncerramento: '+observacao).strip()
    inv.status='CANCELADO' if cancelar else 'CONCLUÍDO'
    inv.unidade_aberta_id=None
    auditar(None,'CANCELAMENTO DE INVENTÁRIO' if cancelar else 'ENCERRAMENTO DE INVENTÁRIO',inventario_id=inv.id,novo=result,observacao=observacao)


def sincronizar_fontes():
    from patio import RelatorioPatio, MotoPatio, LocalizacaoMoto
    defaults()
    for source in db.session.scalars(select(RelatorioPatio).order_by(RelatorioPatio.emitido_em,RelatorioPatio.id)):
        chave='pdf:'+source.sha256
        if db.session.scalar(select(ImportacaoEstoque.id).where(ImportacaoEstoque.chave==chave)):
            continue
        data=json.loads(source.dados); criadas=atualizadas=parciais=0
        for row in data['rows']:
            try:
                vin=normalizar_chassi(row.get('chassi'))
            except ValueError:
                parciais+=1; continue
            m=db.session.scalar(select(MotoEstoque).where(MotoEstoque.chassi_normalizado==vin))
            if source.fonte=='posicao':
                if m and 'FATURADAS' in row.get('secao',''):
                    before=estado(m); m.status_comercial='FATURADA'
                    if row.get('numero_nf'):m.numero_nf=row['numero_nf']
                    auditar(m,'IMPORTAÇÃO FINANCEIRA',before,source.arquivo)
                continue
            if not m:
                year=row.get('ano','').split('/')
                fields=dict(chassi=vin,modelo=row['modelo'],cor=row.get('cor',''),unidade=source.unidade,
                    ano_fabricacao='20'+year[0] if year and len(year[0])==2 else '',ano_modelo='20'+year[-1] if year and len(year[-1])==2 else '',
                    status_comercial='AGUARDANDO APROVAÇÃO' if 'aprova' in row.get('situacao','').lower() else 'DISPONÍVEL')
                m=cadastrar(fields,source.arquivo); criadas+=1
            else:
                before=estado(m); m.modelo=row['modelo']; m.cor=row.get('cor',m.cor)
                # Não muda unidade, localização, entrada ou saída de moto já controlada.
                m.status_comercial='AGUARDANDO APROVAÇÃO' if 'aprova' in row.get('situacao','').lower() else 'DISPONÍVEL'
                auditar(m,'ATUALIZAÇÃO DE FONTE',before,source.arquivo); atualizadas+=1
            if m.data_entrada is None and row.get('dias') is not None:
                m.data_entrada=source.emitido_em.date()-timedelta(days=int(row['dias']))
            m.origem_dado=source.arquivo
        db.session.add(ImportacaoEstoque(chave=chave,fonte=source.fonte,arquivo=source.arquivo,usuario=ator()[1],resultado=dict(criadas=criadas,atualizadas=atualizadas,parciais_separados=parciais)))
        db.session.flush()
    legacy_rows=db.session.scalars(select(MotoPatio).order_by(MotoPatio.id)).all()
    legacy_groups={}
    for row in legacy_rows:
        try: legacy_groups.setdefault(normalizar_chassi(row.chassi),[]).append(row.id)
        except ValueError: pass
    for source in legacy_rows:
        try:
            vin=normalizar_chassi(source.chassi)
        except ValueError:
            continue
        chave='planilha:'+str(source.id)+':'+hashlib.sha256((source.arquivo+str(source.atualizado_em)).encode()).hexdigest()
        if db.session.scalar(select(ImportacaoEstoque.id).where(ImportacaoEstoque.chave==chave)):
            continue
        m=db.session.scalar(select(MotoEstoque).where(MotoEstoque.chassi_normalizado==vin))
        if m is None:
            from models import Configuracao
            config=db.session.get(Configuracao,1)
            m=cadastrar(dict(chassi=vin,modelo=source.modelo,cor=source.cor,unidade=source.unidade or (config.unidade if config else 'Não informada'),status_comercial=status_fonte(source.situacao)),source.arquivo)
        else:
            before=estado(m);m.modelo=source.modelo;m.cor=source.cor;m.status_comercial=status_fonte(source.situacao)
            auditar(m,'ATUALIZAÇÃO DE PLANILHA',before,source.arquivo)
        if len(legacy_groups[vin])>1 and not db.session.scalar(select(DivergenciaMoto.id).where(DivergenciaMoto.chassi==vin,DivergenciaMoto.tipo=='CHASSI DUPLICADO')):
            db.session.add(DivergenciaMoto(moto_id=m.id,chassi=vin,tipo='CHASSI DUPLICADO',esperado='Um cadastro por chassi normalizado',encontrado=f'Registros legados {legacy_groups[vin]}; originais preservados.',responsavel=ator()[1]))
            auditar(m,'DUPLICIDADE LEGADA',observacao='Fontes preservadas; um único mestre por chassi.')
        db.session.add(ImportacaoEstoque(chave=chave,fonte='planilha',arquivo=source.arquivo,usuario=ator()[1],resultado=dict(moto_id=m.id)))
    for legacy in db.session.scalars(select(LocalizacaoMoto)):
        chave='localizacao-legada:'+legacy.chassi+':'+legacy.atualizado_em.isoformat()
        if db.session.scalar(select(ImportacaoEstoque.id).where(ImportacaoEstoque.chave==chave)):
            continue
        try:
            vin=normalizar_chassi(legacy.chassi)
        except ValueError:
            continue
        m=db.session.scalar(select(MotoEstoque).where(MotoEstoque.chassi_normalizado==vin))
        legacy_time=legacy.atualizado_em.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)
        if m and (m.data_ultima_confirmacao is None or legacy_time>m.data_ultima_confirmacao):
            destino={'Dentro da oficina':'OFICINA','Em trânsito':'TRANSITO'}.get(legacy.localizacao,'A_CONFIRMAR')
            if destino!='A_CONFIRMAR':
                mover(m,destino,'Localização manual legada; autor original não registrado.','MIGRAÇÃO')
                m.data_ultima_confirmacao=legacy_time
                m.usuario_ultima_confirmacao='Confirmação legada / autor não registrado'
        db.session.add(ImportacaoEstoque(chave=chave,fonte='localizacao-legada',arquivo='localizacao_moto',usuario=ator()[1],resultado=dict(chassi=vin)))
    db.session.flush()


def indicadores(rows=None):
    rows=rows if rows is not None else db.session.scalars(select(MotoEstoque).options(selectinload(MotoEstoque.localizacao))).all()
    active=[m for m in rows if m.ativo and not m.saida_fisica_confirmada and m.presenca_confirmada]
    pending={d.moto_id for d in db.session.scalars(select(DivergenciaMoto).where(DivergenciaMoto.resolvido.is_(False)))}
    localizadas=sum(m.presenca_confirmada for m in active)
    counts=Counter(m.localizacao.grupo for m in active)
    reconciled=sum(m.presenca_confirmada and m.id not in pending for m in active)
    return dict(entregas_hoje=len(entregas_periodo(agora().date(),agora().date(),request.args.get('unidade','') if has_request_context() else '')),total=len(active),localizadas=localizadas,a_confirmar=sum(m.data_ultima_confirmacao is None or m.localizacao.grupo=='A_CONFIRMAR' for m in active),
        divergencias=sum(m.id in pending for m in active),por_local=dict(counts),por_codigo=dict(Counter(m.localizacao.codigo for m in active)),conciliacao=round(reconciled*100/len(active),2) if active else 0,
        saidas_hoje=sum(m.saida_fisica_confirmada and m.data_saida_fisica and m.data_saida_fisica.date()==agora().date() for m in rows))


def conferencia_status(m,policy):
    if not m.data_ultima_confirmacao:
        return 'NUNCA CONFERIDA'
    days=(agora().date()-m.data_ultima_confirmacao.date()).days
    return 'CONFERIDA HOJE' if days==0 else 'CONFERIDA RECENTEMENTE' if days<=policy.recente_dias else 'CONFERÊNCIA VENCIDA' if days>=policy.vencida_dias else 'CONFERÊNCIA A RENOVAR'

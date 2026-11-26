"""
RNF03 - exportação dos dados da conta (direito de acesso e de portabilidade,
LGPD art. 18).

Junta, num único dicionário pronto para virar JSON, tudo o que o app guarda
sobre a pessoa: conta, preferências, campanhas, comentários, mensagens de chat,
avaliações, avisos e textos barrados pela moderação.

Fica de fora, de propósito:
- o hash da senha e os tokens de confirmação e de recuperação (segredos);
- dados de OUTRAS pessoas: e-mails dos inscritos nas campanhas dela, o texto
  das mensagens e comentários dos outros. As campanhas trazem só a contagem de
  inscritos.
"""

import base64
import datetime

from campanhas.models import Avaliacao, Campanha
from chat.models import MensagemChat
from core.horario import UTC
from moderacao.models import ConteudoBloqueado
from notificacoes.models import Notificacao

from .models import FotoPerfil

FORMATO = "Sessão Zero - exportação dos dados da conta (versão 1)"


def _iso(data):
    """Datas ficam em UTC no banco; saem em ISO 8601 com 'Z'."""
    if data is None:
        return None
    return data.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _titulos(ids):
    """{id da campanha: título}, para as mensagens de chat. Campanha excluída
    não aparece (o título sai como None)."""
    titulos = {}
    for campanha in Campanha.objects(id__in=[i for i in ids if i]).only("titulo"):
        titulos[str(campanha.id)] = campanha.titulo
    return titulos


def montar_exportacao(usuario):
    email = usuario.email

    conta = {
        "nome_de_usuario": usuario.username,
        "email": usuario.email,
        "biografia": usuario.bio or "",
        "criada_em": _iso(usuario.criado_em),
        "fuso_horario": usuario.fuso_horario,
        "receber_avisos_por_email": usuario.notificar_por_email,
        "preferencias": usuario.preferencias or {},
        "avatar": {
            "desenho": usuario.avatar_preset or None,
            "tem_foto": bool(usuario.tem_foto),
        },
        "politica_de_privacidade": {
            "aceita_em": _iso(usuario.politica_aceita_em),
            "versao": usuario.politica_versao,
        },
    }
    if usuario.tem_foto:
        foto = FotoPerfil.objects(usuario_id=str(usuario.id)).first()
        if foto is not None:
            conta["foto_de_perfil_jpeg_base64"] = base64.b64encode(bytes(foto.dados)).decode()

    mestradas = [
        {
            "id": str(c.id),
            "titulo": c.titulo,
            "sinopse": c.sinopse,
            "sistema_rpg": c.sistema_rpg,
            "classificacao_indicativa": c.classificacao,
            "temas_sensiveis": list(c.temas_sensiveis),
            "max_jogadores": c.max_jogadores,
            "jogadores_inscritos": len(c.jogadores_inscritos_emails),
            "status": c.status,
            "data_da_primeira_sessao": _iso(c.data_sessao),
            "recorrencia": c.recorrencia,
            "fuso_do_mestre": c.fuso_mestre,
            "criada_em": _iso(c.criado_em),
        }
        for c in Campanha.objects(mestre_email=email)
    ]

    inscrito = [
        {
            "id": str(c.id),
            "titulo": c.titulo,
            "mestre": c.mestre_username,
            "sistema_rpg": c.sistema_rpg,
            "status": c.status,
            "data_da_primeira_sessao": _iso(c.data_sessao),
        }
        for c in Campanha.objects(jogadores_inscritos_emails=email)
    ]

    comentarios = [
        {
            "campanha_id": str(c.id),
            "campanha": c.titulo,
            "texto": comentario.texto,
            "escrito_em": _iso(comentario.criado_em),
        }
        for c in Campanha.objects(comentarios__autor_email=email)
        for comentario in c.comentarios
        if comentario.autor_email == email
    ]

    mensagens = list(MensagemChat.objects(autor_email=email).order_by("criado_em"))
    titulos = _titulos({m.campanha_id for m in mensagens})
    chat = [
        {
            "campanha_id": m.campanha_id,
            "campanha": titulos.get(m.campanha_id),
            "texto": m.texto,
            "enviada_em": _iso(m.criado_em),
        }
        for m in mensagens
    ]

    avaliacoes_feitas = [
        {
            "campanha": a.campanha_titulo,
            "avaliado": a.avaliado_username,
            "papel_do_avaliado": a.papel_avaliado,
            "nota": a.nota,
            "comentario": a.comentario,
            "feita_em": _iso(a.criado_em),
            "atualizada_em": _iso(a.atualizado_em),
        }
        for a in Avaliacao.objects(avaliador_email=email)
    ]
    avaliacoes_recebidas = [
        {
            "campanha": a.campanha_titulo,
            "avaliador": a.avaliador_username,
            "papel_como_avaliado": a.papel_avaliado,
            "nota": a.nota,
            "comentario": a.comentario,
            "feita_em": _iso(a.criado_em),
        }
        for a in Avaliacao.objects(avaliado_email=email)
    ]

    avisos = [
        {"texto": n.texto, "link": n.url, "lida": n.lida, "em": _iso(n.criado_em)}
        for n in Notificacao.objects(destinatario_email=email).order_by("criado_em")
    ]

    bloqueados = [
        {
            "texto": b.texto_original,
            "motivo": b.motivo,
            "origem": b.origem,
            "em": _iso(b.criado_em),
        }
        for b in ConteudoBloqueado.objects(autor_email=email).order_by("criado_em")
    ]

    return {
        "formato": FORMATO,
        "gerado_em": _iso(datetime.datetime.utcnow()),
        "conta": conta,
        "campanhas_que_mestro": mestradas,
        "campanhas_em_que_estou_inscrito": inscrito,
        "meus_comentarios": comentarios,
        "minhas_mensagens_de_chat": chat,
        "avaliacoes_que_fiz": avaliacoes_feitas,
        "avaliacoes_que_recebi": avaliacoes_recebidas,
        "avisos_recebidos": avisos,
        "textos_barrados_pela_moderacao": bloqueados,
    }

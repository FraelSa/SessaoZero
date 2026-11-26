"""
RF01 - exclusão de conta.

Excluir a conta apaga o que é da pessoa e anonimiza o que ela escreveu em
espaços compartilhados:

- campanhas que ela mestra são excluídas (com as mensagens do chat), e os
  jogadores inscritos são avisados;
- nas campanhas em que ela é jogadora, a inscrição é removida, a vaga volta a
  ficar livre (a campanha lotada reabre) e o mestre é avisado;
- comentários, mensagens de chat, avaliações escritas por ela e registros da
  moderação ficam, mas sem identificação: o autor vira "[conta excluída]";
- as avaliações que ela recebeu (RF06) são apagadas;
- foto de perfil, notificações, cadastro pendente e o próprio usuário somem.
"""

from campanhas.models import Avaliacao, Campanha
from chat.models import MensagemChat
from moderacao.models import ConteudoBloqueado
from notificacoes.models import Notificacao
from notificacoes.servicos import notificar, notificar_varios

from .models import CadastroPendente, FotoPerfil

AUTOR_REMOVIDO = "[conta excluída]"
EMAIL_REMOVIDO = "conta-excluida"


def resumo_da_exclusao(usuario):
    """Quantas campanhas seriam excluídas e de quantas a pessoa sairia; usado
    na tela de confirmação."""
    return {
        "campanhas_mestradas": Campanha.objects(mestre_email=usuario.email).count(),
        "campanhas_inscrito": Campanha.objects(
            jogadores_inscritos_emails=usuario.email
        ).count(),
    }


def excluir_conta(usuario):
    """Exclui a conta e devolve o resumo do que foi feito."""
    email = usuario.email
    resumo = resumo_da_exclusao(usuario)

    # 1) Campanhas que a pessoa mestra: avisa os inscritos e apaga.
    for campanha in Campanha.objects(mestre_email=email):
        notificar_varios(
            campanha.jogadores_inscritos_emails,
            f'A campanha "{campanha.titulo}" foi encerrada: o mestre excluiu a conta.',
        )
        MensagemChat.objects(campanha_id=str(campanha.id)).delete()
        campanha.delete()

    # 2) Campanhas em que ela é jogadora: libera a vaga e avisa o mestre.
    for campanha in Campanha.objects(jogadores_inscritos_emails=email):
        campanha.jogadores_inscritos_emails.remove(email)
        campanha.sincronizar_status()
        campanha.save()
        notificar(
            campanha.mestre_email,
            f'{usuario.username} excluiu a conta e saiu da sua campanha '
            f'"{campanha.titulo}". Uma vaga foi liberada.',
        )

    # 3) Comentários: ficam, sem identificação.
    for campanha in Campanha.objects(comentarios__autor_email=email):
        for comentario in campanha.comentarios:
            if comentario.autor_email == email:
                comentario.autor_email = EMAIL_REMOVIDO
                comentario.autor_username = AUTOR_REMOVIDO
        campanha.save()

    # 4) Chat e moderação: ficam, sem identificação.
    MensagemChat.objects(autor_email=email).update(
        set__autor_email=EMAIL_REMOVIDO, set__autor_username=AUTOR_REMOVIDO
    )
    ConteudoBloqueado.objects(autor_email=email).update(set__autor_email=EMAIL_REMOVIDO)

    # 4b) Avaliações (RF06): as recebidas somem; as escritas ficam, sem o nome
    # (o e-mail ganha o id para não repetir a chave única do índice).
    Avaliacao.objects(avaliado_email=email).delete()
    for avaliacao in Avaliacao.objects(avaliador_email=email):
        avaliacao.avaliador_email = f"{EMAIL_REMOVIDO}-{avaliacao.id}"
        avaliacao.avaliador_username = AUTOR_REMOVIDO
        avaliacao.save()

    # 5) Dados da própria pessoa.
    Notificacao.objects(destinatario_email=email).delete()
    FotoPerfil.objects(usuario_id=str(usuario.id)).delete()
    CadastroPendente.objects(email=email).delete()
    usuario.delete()

    return resumo

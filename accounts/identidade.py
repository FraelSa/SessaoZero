"""
RF01 - mudar o nome de usuário e o e-mail da conta.

O app guarda o nome de usuário e, principalmente, o e-mail da pessoa em várias
coleções (modelo orientado a documentos: sem JOINs, cada documento carrega o
que precisa para ser exibido). Por isso trocar um deles não é só mudar o
Usuario: as cópias precisam acompanhar, ou a pessoa perde as próprias campanhas,
inscrições, avisos e avaliações.

O MongoDB não faz transação entre coleções aqui, então a ordem importa:

- as cópias são atualizadas primeiro e o Usuario por último, e cada passo pode
  ser repetido sem efeito colateral. Se algo falhar no meio da troca de e-mail,
  o link de confirmação continua valendo e basta clicar de novo;
- a troca de nome faz o contrário: o Usuario vai primeiro porque o índice único
  do MongoDB é quem garante que ninguém leve o mesmo nome ao mesmo tempo.

O que NÃO muda: texto de avisos já enviados (ficam como foram escritos) e a
foto de perfil (ligada ao id do usuário, não ao nome ou ao e-mail).
"""

from django.urls import reverse

from campanhas.models import Avaliacao, Campanha
from chat.models import MensagemChat
from moderacao.models import ConteudoBloqueado
from notificacoes.models import Notificacao


def trocar_username(usuario, novo_username):
    """Muda o nome de usuário e acerta as cópias dele em campanhas, comentários,
    chat e avaliações. Levanta NotUniqueError se o nome já for de outra conta."""
    antigo = usuario.username
    email = usuario.email

    usuario.username = novo_username
    usuario.save()

    Campanha.objects(mestre_email=email).update(set__mestre_username=novo_username)

    for campanha in Campanha.objects(comentarios__autor_email=email):
        for comentario in campanha.comentarios:
            if comentario.autor_email == email:
                comentario.autor_username = novo_username
        campanha.save()

    MensagemChat.objects(autor_email=email).update(set__autor_username=novo_username)
    Avaliacao.objects(avaliador_email=email).update(set__avaliador_username=novo_username)
    Avaliacao.objects(avaliado_email=email).update(set__avaliado_username=novo_username)

    # Os avisos "fulano avaliou você" levam ao perfil público; o link antigo
    # deixaria de existir com o nome.
    Notificacao.objects(
        destinatario_email=email, url=reverse("perfil_publico", args=[antigo])
    ).update(set__url=reverse("perfil_publico", args=[novo_username]))


def trocar_email(usuario, novo_email):
    """Muda o e-mail da conta e acerta tudo que o usa como chave: campanhas
    mestradas, inscrições, comentários, chat, avaliações, avisos e registros da
    moderação. Quem chama já confirmou que `novo_email` é de quem pediu e que
    nenhuma outra conta o usa."""
    antigo = usuario.email

    Campanha.objects(mestre_email=antigo).update(set__mestre_email=novo_email)

    # A inscrição é um item de lista: entra o novo e só então sai o antigo, para
    # a pessoa nunca ficar fora da mesa, mesmo que algo pare entre os dois passos.
    Campanha.objects(jogadores_inscritos_emails=antigo).update(
        add_to_set__jogadores_inscritos_emails=novo_email
    )
    Campanha.objects(jogadores_inscritos_emails=antigo).update(
        pull__jogadores_inscritos_emails=antigo
    )

    for campanha in Campanha.objects(comentarios__autor_email=antigo):
        for comentario in campanha.comentarios:
            if comentario.autor_email == antigo:
                comentario.autor_email = novo_email
        campanha.save()

    MensagemChat.objects(autor_email=antigo).update(set__autor_email=novo_email)
    Avaliacao.objects(avaliador_email=antigo).update(set__avaliador_email=novo_email)
    Avaliacao.objects(avaliado_email=antigo).update(set__avaliado_email=novo_email)
    Notificacao.objects(destinatario_email=antigo).update(set__destinatario_email=novo_email)
    ConteudoBloqueado.objects(autor_email=antigo).update(set__autor_email=novo_email)

    # Por último, a própria conta (e o pedido de troca deixa de existir).
    usuario.email = novo_email
    usuario.novo_email = None
    usuario.token_novo_email = None
    usuario.token_novo_email_expira_em = None
    # Um link de recuperação de senha enviado ao e-mail antigo deixa de valer.
    usuario.token_recuperacao_senha = None
    usuario.token_recuperacao_expira_em = None
    usuario.save()

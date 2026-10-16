"""
Consumer do chat em tempo real de cada campanha.

Cada campanha tem sua própria "sala" (grupo de canal), identificada pelo
id da campanha. MongoEngine é síncrono, então qualquer acesso ao banco
dentro do consumer (que é assíncrono) passa por
`channels.db.database_sync_to_async`, que roda o código síncrono numa
thread separada sem travar o loop de eventos.
"""

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from accounts.models import Usuario
from campanhas.utils import buscar_campanha_ou_404
from core.horario import para_horario_local
from moderacao.filtros import moderar_texto
from moderacao.models import ConteudoBloqueado

from .models import MensagemChat


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.campanha_id = self.scope["url_route"]["kwargs"]["campanha_id"]
        self.grupo = f"chat_{self.campanha_id}"

        usuario = await self._usuario_da_sessao()
        pode_entrar = usuario is not None and await self._usuario_participa(usuario)

        if not pode_entrar:
            # Sem login, campanha inexistente, ou usuário que não é nem
            # mestre nem jogador inscrito: recusa a conexão.
            await self.close()
            return

        self.usuario = usuario

        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "grupo"):
            await self.channel_layer.group_discard(self.grupo, self.channel_name)

    async def receive(self, text_data):
        try:
            dados = json.loads(text_data)
            texto = (dados.get("texto") or "").strip()
        except (json.JSONDecodeError, AttributeError):
            return

        if not texto:
            return

        if len(texto) > 1000:
            # O maxlength do <input> no template só protege contra
            # digitação manual — um cliente WebSocket "cru" poderia
            # mandar qualquer tamanho, o que quebraria ao salvar
            # (MensagemChat.texto tem max_length=1000).
            await self.send(
                text_data=json.dumps(
                    {"tipo": "erro", "motivo": "Mensagem muito longa (máximo 1000 caracteres)."}
                )
            )
            return

        # RNF04 - moderação em tempo real, antes de salvar ou distribuir a
        # mensagem para os outros participantes.
        aceito, motivo = moderar_texto(texto)
        if not aceito:
            await self._registrar_bloqueio(texto, motivo)
            # Erro vai só para quem enviou (não é broadcast para o grupo).
            await self.send(text_data=json.dumps({"tipo": "erro", "motivo": motivo}))
            return

        mensagem = await self._salvar_mensagem(texto)

        await self.channel_layer.group_send(
            self.grupo,
            {
                "type": "mensagem_chat",
                "autor_username": mensagem.autor_username,
                "texto": mensagem.texto,
                "criado_em": para_horario_local(mensagem.criado_em).strftime("%H:%M"),
            },
        )

    async def mensagem_chat(self, evento):
        """Handler chamado quando alguém do grupo manda uma mensagem —
        repassa para o WebSocket deste usuário específico."""
        await self.send(
            text_data=json.dumps(
                {
                    "tipo": "mensagem",
                    "autor_username": evento["autor_username"],
                    "texto": evento["texto"],
                    "criado_em": evento["criado_em"],
                }
            )
        )

    # -- Helpers síncronos (acesso ao MongoEngine) --------------------

    @database_sync_to_async
    def _usuario_da_sessao(self):
        usuario_id = self.scope.get("session", {}).get("usuario_id")
        if not usuario_id:
            return None
        return Usuario.objects(id=usuario_id, ativo=True).first()

    @database_sync_to_async
    def _usuario_participa(self, usuario):
        try:
            campanha = buscar_campanha_ou_404(self.campanha_id)
        except Exception:  # noqa: BLE001 - Http404 ou id inválido
            return False
        return usuario.email == campanha.mestre_email or (
            usuario.email in campanha.jogadores_inscritos_emails
        )

    @database_sync_to_async
    def _salvar_mensagem(self, texto):
        return MensagemChat.objects.create(
            campanha_id=self.campanha_id,
            autor_email=self.usuario.email,
            autor_username=self.usuario.username,
            texto=texto,
        )

    @database_sync_to_async
    def _registrar_bloqueio(self, texto, motivo):
        ConteudoBloqueado.objects.create(
            autor_email=self.usuario.email,
            texto_original=texto,
            motivo=motivo,
            origem=f"chat:{self.campanha_id}",
        )

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sessao_zero.settings")

# get_asgi_application() já chama django.setup() por baixo dos panos; só
# depois disso é seguro importar módulos que dependem dos apps carregados
# (como chat.routing, que importa chat.consumers, que importa models).
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.sessions import SessionMiddlewareStack  # noqa: E402

import chat.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # SessionMiddlewareStack lê a sessão do Django (o mesmo cookie
        # usado nas views HTTP normais), o que é suficiente pro nosso
        # esquema de login baseado em request.session (ver
        # accounts/auth_utils.py) — não precisamos do AuthMiddlewareStack
        # padrão do Channels, que espera o User model do Django.
        "websocket": SessionMiddlewareStack(
            URLRouter(chat.routing.websocket_urlpatterns)
        ),
    }
)

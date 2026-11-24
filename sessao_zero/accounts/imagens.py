"""
Tratamento da foto de perfil enviada pelo usuário.

A foto nunca é guardada como veio: ela é validada, cortada em quadrado,
reduzida para 256x256 e regravada como JPEG. Isso mantém o banco leve (uns
15 a 30 KB por foto) e descarta metadados como a localização do GPS.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

TAMANHO_MAXIMO_ARQUIVO = 2 * 1024 * 1024  # 2 MB
LADO = 256
PIXELS_MAXIMOS = 25_000_000  # evita imagens enormes que travam o servidor
FORMATOS_ACEITOS = {"JPEG", "PNG", "WEBP", "GIF"}


def processar_foto(arquivo):
    """Recebe um arquivo enviado e devolve os bytes do JPEG final.
    Levanta ValueError, com uma mensagem pronta para o usuário, se o
    arquivo não servir."""
    if arquivo.size > TAMANHO_MAXIMO_ARQUIVO:
        raise ValueError("A foto deve ter no máximo 2 MB.")

    try:
        imagem = Image.open(arquivo)
        if imagem.format not in FORMATOS_ACEITOS:
            raise ValueError("Formato não aceito. Envie uma imagem JPG, PNG, WEBP ou GIF.")
        if imagem.width * imagem.height > PIXELS_MAXIMOS:
            raise ValueError("Essa imagem é grande demais. Envie uma menor.")

        imagem = ImageOps.exif_transpose(imagem)

        if imagem.mode in ("RGBA", "LA") or (imagem.mode == "P" and "transparency" in imagem.info):
            imagem = imagem.convert("RGBA")
            fundo = Image.new("RGB", imagem.size, (255, 255, 255))
            fundo.paste(imagem, mask=imagem.split()[-1])
            imagem = fundo
        else:
            imagem = imagem.convert("RGB")

        imagem = ImageOps.fit(imagem, (LADO, LADO), Image.LANCZOS)

        saida = io.BytesIO()
        imagem.save(saida, format="JPEG", quality=85, optimize=True)
        return saida.getvalue()
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("Não foi possível ler essa imagem. Tente outro arquivo.")

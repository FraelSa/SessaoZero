"""
RNF01 - arquivos estáticos (CSS, fontes, imagens, JavaScript) com nome que muda
quando o conteúdo muda.

`collectstatic` copia cada arquivo com um trecho do seu resumo no nome
("sessao_zero.3f9a1c07d2b4.css") e o WhiteNoise passa a mandá-lo com cache de 1 ano:
quem já visitou o site não baixa nada de novo, e, quando o arquivo muda, o nome
muda junto e todos recebem a versão nova na hora. Os arquivos também saem
comprimidos (gzip).
"""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class ArmazenamentoDeEstaticos(CompressedManifestStaticFilesStorage):
    # Um arquivo que não está no manifesto (esquecido no collectstatic) não derruba
    # a página com erro: usa-se o nome simples, que o WhiteNoise também atende.
    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            # Sem `collectstatic` (desenvolvimento, testes) a pasta de destino não
            # existe, e o Django não tem de onde tirar o resumo: o nome fica como está.
            return name

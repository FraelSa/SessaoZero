"""
Datas e fusos horários.

Regra do projeto: toda data/hora gravada no MongoDB fica em UTC, sem fuso
(datetime.datetime.utcnow() e afins). Na hora de mostrar, converte-se para o
fuso da pessoa que está vendo a página: o `FusoHorarioMiddleware` ativa o fuso
escolhido em Preferências (ou o padrão, America/Bahia) a cada requisição, e o
filtro `|local` (core/templatetags/horario.py) usa o fuso ativo.

Na hora de gravar, o horário digitado pelo mestre é interpretado no fuso dele
(o fuso ativo na requisição) e convertido para UTC por `para_utc_ingenuo`.
Assim o horário da sessão (RD04) aparece certo para jogadores em fusos
diferentes.
"""

import calendar
import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

UTC = datetime.timezone.utc

FUSO_PADRAO = "America/Bahia"

# (nome IANA, texto mostrado). O Brasil não tem horário de verão desde 2019,
# mas os fusos de fora têm; por isso a recorrência é calculada no fuso do mestre
# (ver `proxima_ocorrencia`).
FUSOS_HORARIOS = (
    ("America/Noronha", "Fernando de Noronha"),
    ("America/Sao_Paulo", "Brasília, São Paulo e Rio de Janeiro"),
    ("America/Bahia", "Salvador, Bahia"),
    ("America/Cuiaba", "Cuiabá, Mato Grosso"),
    ("America/Manaus", "Manaus, Amazonas"),
    ("America/Rio_Branco", "Rio Branco, Acre"),
    ("America/Argentina/Buenos_Aires", "Buenos Aires"),
    ("America/New_York", "Nova York"),
    ("Europe/Lisbon", "Lisboa"),
    ("Europe/London", "Londres"),
)
IDS_FUSOS = tuple(nome for nome, _ in FUSOS_HORARIOS)

RECORRENCIAS = (
    ("unica", "Sessão única (one-shot)"),
    ("semanal", "Toda semana"),
    ("quinzenal", "A cada 15 dias"),
    ("mensal", "Todo mês"),
)


def zona_segura(nome):
    """ZoneInfo para o nome dado; se o nome for inválido ou desconhecido,
    cai no fuso padrão em vez de derrubar a página."""
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError, TypeError, OSError):
        return ZoneInfo(FUSO_PADRAO)


def rotulo_fuso(nome):
    return dict(FUSOS_HORARIOS).get(nome, nome)


def deslocamento_utc(valor):
    """'UTC-03:00' para um datetime com fuso."""
    desloc = valor.utcoffset() or datetime.timedelta(0)
    minutos = int(desloc.total_seconds() // 60)
    sinal = "-" if minutos < 0 else "+"
    minutos = abs(minutos)
    return f"UTC{sinal}{minutos // 60:02d}:{minutos % 60:02d}"


def para_horario_local(valor):
    """Converte um datetime gravado em UTC (sem fuso) para o fuso ativo."""
    if valor is None:
        return None
    if timezone.is_naive(valor):
        valor = timezone.make_aware(valor, UTC)
    return timezone.localtime(valor)


def para_utc_ingenuo(valor):
    """Converte para UTC sem fuso, que é como as datas ficam no MongoDB.
    Um datetime sem fuso é interpretado no fuso ativo (o de quem digitou)."""
    if valor is None:
        return None
    if timezone.is_naive(valor):
        valor = timezone.make_aware(valor)
    return valor.astimezone(UTC).replace(tzinfo=None)


def para_utc_com_fuso(valor):
    """UTC sem fuso (como vem do MongoDB) -> UTC com fuso, para mostrar em
    formulários. Aceita None."""
    if valor is None:
        return None
    if timezone.is_naive(valor):
        return valor.replace(tzinfo=UTC)
    return valor.astimezone(UTC)


def _somar_meses(valor, meses):
    total = valor.month - 1 + meses
    ano = valor.year + total // 12
    mes = total % 12 + 1
    dia = min(valor.day, calendar.monthrange(ano, mes)[1])
    return valor.replace(year=ano, month=mes, day=dia)


def proxima_ocorrencia(inicio_utc, recorrencia, nome_fuso, agora_utc=None):
    """Primeira sessão em ou depois de `agora_utc`.

    `inicio_utc` é a data gravada (UTC sem fuso) de uma sessão. Para sessão
    única, ou se ela ainda está no futuro, devolve a própria data. Para as
    recorrentes, avança de semana em semana, de 15 em 15 dias ou de mês em mês,
    sempre no mesmo horário de relógio do fuso do mestre (por isso o horário
    de verão, nos fusos que o têm, não desloca a sessão). Devolve UTC sem fuso.
    """
    if inicio_utc is None:
        return None
    agora = agora_utc or datetime.datetime.utcnow()
    if recorrencia not in ("semanal", "quinzenal", "mensal") or inicio_utc >= agora:
        return inicio_utc

    zona = zona_segura(nome_fuso)
    inicio_local = inicio_utc.replace(tzinfo=UTC).astimezone(zona)

    if recorrencia == "mensal":
        dias_por_passo = 28  # estimativa por baixo; o laço abaixo acerta

        def candidato(passo):
            return _somar_meses(inicio_local, passo)
    else:
        dias_por_passo = 7 if recorrencia == "semanal" else 14

        def candidato(passo):
            # Soma de relógio no fuso do mestre: o horário local se mantém.
            return inicio_local + datetime.timedelta(days=dias_por_passo * passo)

    def em_utc(passo):
        return candidato(passo).astimezone(UTC).replace(tzinfo=None)

    # Começa um pouco antes do estimado e avança até alcançar `agora`; depois
    # recua se a estimativa tiver passado do ponto.
    passo = max((agora - inicio_utc).days // dias_por_passo - 1, 1)
    while em_utc(passo) < agora:
        passo += 1
    while passo > 1 and em_utc(passo - 1) >= agora:
        passo -= 1
    return em_utc(passo)


def descrever_sessao(campanha):
    """Dados prontos para a tela de detalhe: o horário da próxima sessão no fuso
    de quem está vendo e, se o fuso do mestre tiver outro deslocamento, também
    no fuso do mestre. None se a sessão ainda não tem data."""
    proxima = campanha.proxima_sessao
    if proxima is None:
        return None

    no_seu_fuso = para_horario_local(proxima)
    nome_atual = timezone.get_current_timezone_name()
    no_fuso_mestre = no_seu_fuso.astimezone(zona_segura(campanha.fuso_mestre))
    mostrar_mestre = (
        campanha.fuso_mestre != nome_atual
        and no_fuso_mestre.utcoffset() != no_seu_fuso.utcoffset()
    )
    return {
        "seu": no_seu_fuso,
        # Só uma sessão única pode estar no passado (as recorrentes avançam
        # sozinhas); a tela troca "Próxima sessão" por "Sessão realizada em".
        "passada": proxima <= datetime.datetime.utcnow(),
        "seu_fuso": rotulo_fuso(nome_atual),
        "seu_utc": deslocamento_utc(no_seu_fuso),
        # Já formatado: o filtro |date converteria um datetime com fuso para o
        # fuso ativo e apagaria justamente a diferença que se quer mostrar.
        "mestre": no_fuso_mestre.strftime("%H:%M") if mostrar_mestre else None,
        "mestre_fuso": rotulo_fuso(campanha.fuso_mestre),
    }

"""Agendador do workflow de verificação de prazos (Caminho 2).

Execução imediata (para testes manuais):
    python -m fase2_agente.automacoes.scheduler --run-now

Execução contínua (produção — dispara todo dia às 08:00):
    python -m fase2_agente.automacoes.scheduler
"""
import argparse
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

# ── Logging: console + arquivo ────────────────────────────────────────────────
_LOG_FILE = Path(__file__).resolve().parents[2] / "logs" / "alertas_prazos.log"
_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
_fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")

_fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_fh.setFormatter(_fmt)

_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)

logging.root.setLevel(logging.INFO)
logging.root.addHandler(_fh)
logging.root.addHandler(_sh)

log = logging.getLogger(__name__)

# ── Workflow ──────────────────────────────────────────────────────────────────
from fase2_agente.automacoes.verificar_prazos import app as workflow  # noqa: E402

_ESTADO_INICIAL = {
    "n_dias": 7,
    "processos": [],
    "grupos": {},
    "emails_enviados": 0,
    "emails_advogados": {},
}


def executar_verificacao() -> None:
    log.info("=== Iniciando verificação de prazos ===")
    try:
        resultado = workflow.invoke(_ESTADO_INICIAL)
        log.info(
            "=== Concluído | processos=%d | grupos=%d | emails=%d ===",
            len(resultado["processos"]),
            len(resultado["grupos"]),
            resultado["emails_enviados"],
        )
    except Exception:
        log.exception("Erro inesperado durante verificação de prazos.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scheduler de alertas de prazos jurídicos"
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Executa o workflow imediatamente e encerra (sem agendamento contínuo)",
    )
    args = parser.parse_args()

    if args.run_now:
        executar_verificacao()
        return

    scheduler = BlockingScheduler(timezone="America/Recife")
    scheduler.add_job(
        executar_verificacao,
        trigger="cron",
        hour=8,
        minute=0,
        id="verificar_prazos_diario",
    )
    log.info("Scheduler iniciado — próxima execução: diariamente às 08:00 (America/Recife)")
    log.info("Log de execuções em: %s", _LOG_FILE)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Scheduler encerrado pelo usuário.")


if __name__ == "__main__":
    main()

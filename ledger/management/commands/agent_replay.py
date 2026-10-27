"""Django management command for offline replay and cryptographic auditing of an AgentRun.

Usage:
    python manage.py agent_replay <run_id>
"""

from django.core.management.base import BaseCommand, CommandError
from ledger.agent_replay import verify_run_replay


class Command(BaseCommand):
    help = "Recompute the hash chain and verify recorded plan offline without model or network calls."

    def add_arguments(self, parser):
        parser.add_argument("run_id", type=int, help="The ID of the AgentRun to replay and verify.")

    def handle(self, *args, **options):
        run_id = options["run_id"]
        result = verify_run_replay(run_id)

        if "error" in result:
            raise CommandError(result["error"])

        chain_str = "yes" if result["chain_valid"] else "no"
        verdict_str = "yes" if result["verifier_verdicts_identical"] else "no"

        self.stdout.write(self.style.MIGRATE_HEADING(f"=== Agent Run #{run_id} Offline Replay Audit ==="))
        self.stdout.write(f"Source:       {result.get('source_label')}")
        self.stdout.write(f"Steps Count:  {result.get('steps_count')}")
        self.stdout.write(f"Actions:      {result.get('actions_count')}")
        if result["chain_valid"]:
            self.stdout.write(self.style.SUCCESS(f"Chain valid:                   {chain_str}"))
        else:
            self.stdout.write(self.style.ERROR(f"Chain valid:                   {chain_str} (TAMPERED OR BROKEN)"))

        if result["verifier_verdicts_identical"]:
            self.stdout.write(self.style.SUCCESS(f"Verifier verdicts identical:   {verdict_str}"))
        else:
            self.stdout.write(self.style.WARNING(f"Verifier verdicts identical:   {verdict_str}"))

        self.stdout.write(
            "Note: Offline replay proves audit trail immutability and determinism. "
            "It verifies that recorded steps match the cryptographic hash chain."
        )

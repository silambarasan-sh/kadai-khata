"""Management command to seed realistic demo data for Tamil Nadu shopkeeper ledger.

Contains 8 fictional Tamil Nadu customers and 40 realistic transactions spread over
the past 60 days. Fully idempotent: running multiple times will not create duplicates.
"""

from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone

from ledger.models import Customer, EntryKind, LedgerEntry


CUSTOMERS_DATA = [
    {"name": "Ravi Kumar", "phone": "9840112345"},
    {"name": "Murugan P", "phone": "9443223456"},
    {"name": "Selvam S", "phone": "9789334567"},
    {"name": "Priya Sundaram", "phone": "9940445678"},
    {"name": "Anitha Ramesh", "phone": "9884556789"},
    {"name": "Karthik Raja", "phone": "9600667890"},
    {"name": "Meenakshi Ammal", "phone": "9444778901"},
    {"name": "Sangeetha V", "phone": "9790889012"},
]

# 40 realistic transactions over 60 days
# days_ago, customer_name, kind, amount, note, source_text
ENTRIES_DATA = [
    # Customer 1: Ravi Kumar (Regular customer with active balance)
    (58, "Ravi Kumar", EntryKind.CREDIT_GIVEN, "450.00", "Pal packet, bread, muttai", "Ravi-ku 450 udhaar groceries"),
    (54, "Ravi Kumar", EntryKind.CREDIT_GIVEN, "220.00", "Cooking oil 500ml, mustard", "Ravi cooking oil 220 udhaar"),
    (48, "Ravi Kumar", EntryKind.PAYMENT_RECEIVED, "500.00", "GPay transfer", "Ravi gpay-la 500 anupittaar"),
    (39, "Ravi Kumar", EntryKind.CREDIT_GIVEN, "680.00", "Aashirvaad aata 5kg, sugar", "Ravi aata packet 680 book pannunga"),
    (22, "Ravi Kumar", EntryKind.PAYMENT_RECEIVED, "600.00", "Cash payment", "Ravi 600 rooba cash kuduthaar"),
    (10, "Ravi Kumar", EntryKind.CREDIT_GIVEN, "350.00", "Toor dhal 1kg, tea powder", "Ravi dhal tea thool 350"),

    # Customer 2: Murugan P (Frequent small purchases)
    (56, "Murugan P", EntryKind.CREDIT_GIVEN, "120.00", "Biscuit, soap, shampoo", "Murugan 120 udhaar"),
    (50, "Murugan P", EntryKind.CREDIT_GIVEN, "85.00", "Vim bar, Surf Excel", "Murugan vim bar 85"),
    (45, "Murugan P", EntryKind.PAYMENT_RECEIVED, "205.00", "Cash settlement", "Murugan balance clear pannitaaru 205 cash"),
    (38, "Murugan P", EntryKind.CREDIT_GIVEN, "310.00", "Cooking oil, spices", "Murugan 310 provisions"),
    (18, "Murugan P", EntryKind.PAYMENT_RECEIVED, "300.00", "UPI QR scan", "Murugan phonpe-la 300 vanthuchu"),
    (4, "Murugan P", EntryKind.CREDIT_GIVEN, "180.00", "Rice 2kg", "Murugan 2kg arisi 180"),

    # Customer 3: Selvam S (Settles in lumpsum)
    (55, "Selvam S", EntryKind.CREDIT_GIVEN, "1250.00", "Ponni raw rice 25kg bag", "Selvam annachi 25kg arisi 1250 udhaar"),
    (42, "Selvam S", EntryKind.CREDIT_GIVEN, "420.00", "Masala samaiyal items", "Selvam 420 masala items"),
    (35, "Selvam S", EntryKind.PAYMENT_RECEIVED, "1500.00", "Bank transfer / GPay", "Selvam gpay 1500 kuduthaaru"),
    (20, "Selvam S", EntryKind.CREDIT_GIVEN, "580.00", "Groundnut oil 1L, ghee", "Selvam nallennai ghee 580"),
    (7, "Selvam S", EntryKind.PAYMENT_RECEIVED, "500.00", "Cash", "Selvam 500 cash payment"),

    # Customer 4: Priya Sundaram (Neighbor, small daily purchases)
    (52, "Priya Sundaram", EntryKind.CREDIT_GIVEN, "90.00", "Curd, milk packet", "Priya thayir paal 90 udhaar"),
    (46, "Priya Sundaram", EntryKind.CREDIT_GIVEN, "140.00", "Snacks, juice", "Priya snacks 140"),
    (40, "Priya Sundaram", EntryKind.PAYMENT_RECEIVED, "230.00", "Google Pay", "Priya 230 gpay pannitaanga"),
    (28, "Priya Sundaram", EntryKind.CREDIT_GIVEN, "160.00", "Cleaning supplies", "Priya harpic soap 160"),
    (14, "Priya Sundaram", EntryKind.CREDIT_GIVEN, "75.00", "Coriander, curry leaves, chili", "Priya kothamalli karuveppilai 75"),
    (3, "Priya Sundaram", EntryKind.PAYMENT_RECEIVED, "200.00", "Cash", "Priya 200 cash kuduthaanga"),

    # Customer 5: Anitha Ramesh (Monthly ration buyer)
    (51, "Anitha Ramesh", EntryKind.CREDIT_GIVEN, "1850.00", "Monthly grocery kit", "Anitha maami monthly grocery 1850"),
    (37, "Anitha Ramesh", EntryKind.PAYMENT_RECEIVED, "1500.00", "Cash part payment", "Anitha 1500 cash kuduthaanga"),
    (26, "Anitha Ramesh", EntryKind.CREDIT_GIVEN, "340.00", "Noodles, biscuits, boost", "Anitha pasangala noodles biscuit 340"),
    (12, "Anitha Ramesh", EntryKind.PAYMENT_RECEIVED, "500.00", "GPay", "Anitha gpay 500"),

    # Customer 6: Karthik Raja (Bachelor / student)
    (49, "Karthik Raja", EntryKind.CREDIT_GIVEN, "65.00", "Cool drinks, chips", "Karthik 65 udhaar"),
    (43, "Karthik Raja", EntryKind.CREDIT_GIVEN, "110.00", "Eggs, bread", "Karthik muttai bread 110"),
    (36, "Karthik Raja", EntryKind.PAYMENT_RECEIVED, "175.00", "PhonePe full settle", "Karthik 175 paytm pannitaapla"),
    (24, "Karthik Raja", EntryKind.CREDIT_GIVEN, "140.00", "Maggie, cheese", "Karthik maggie cheese 140"),
    (8, "Karthik Raja", EntryKind.CREDIT_GIVEN, "80.00", "Water can 20L", "Karthik water can 80"),

    # Customer 7: Meenakshi Ammal (Elderly customer, accounts settled by son)
    (57, "Meenakshi Ammal", EntryKind.CREDIT_GIVEN, "480.00", "Pooja camphor, oil, agarbatti", "Meenakshi paatti pooja items 480"),
    (44, "Meenakshi Ammal", EntryKind.CREDIT_GIVEN, "320.00", "Wheat flour, ragi flour", "Meenakshi maavu items 320"),
    (31, "Meenakshi Ammal", EntryKind.PAYMENT_RECEIVED, "800.00", "Son sent via GPay", "Meenakshi payyan gpay-la 800 anupunaan"),
    (15, "Meenakshi Ammal", EntryKind.CREDIT_GIVEN, "260.00", "Horlicks, biscuits", "Meenakshi horlicks 260"),

    # Customer 8: Sangeetha V (Tailor shop owner next door)
    (53, "Sangeetha V", EntryKind.CREDIT_GIVEN, "250.00", "Tea, snacks for workers", "Sangeetha tea biscuit 250"),
    (33, "Sangeetha V", EntryKind.CREDIT_GIVEN, "180.00", "Coffee, cool drinks", "Sangeetha tailor shop 180"),
    (19, "Sangeetha V", EntryKind.PAYMENT_RECEIVED, "400.00", "Cash payment", "Sangeetha akka 400 kuduthaanga"),
    (2, "Sangeetha V", EntryKind.CREDIT_GIVEN, "150.00", "Evening snacks", "Sangeetha 150 udhaar"),
]


class Command(BaseCommand):
    help = "Seed 8 fictional Tamil Nadu customers and 40 realistic ledger transactions (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--if-empty",
            "--only-if-empty",
            action="store_true",
            help="Only seed if there are currently no customers in the database.",
        )

    def handle(self, *args, **options):
        if options.get("if_empty") and Customer.objects.exists():
            self.stdout.write(self.style.NOTICE("[Seed Skipped] Customers already exist in database."))
            return

        now = timezone.now()

        created_customers = 0
        existing_customers = 0
        customer_map = {}

        for c_data in CUSTOMERS_DATA:
            customer, created = Customer.objects.get_or_create(
                name=c_data["name"],
                defaults={
                    "phone": c_data["phone"],
                    "created_at": now - timedelta(days=60),
                },
            )
            if created:
                created_customers += 1
            else:
                existing_customers += 1
                if not customer.phone and c_data["phone"]:
                    customer.phone = c_data["phone"]
                    customer.save(update_fields=["phone"])
            customer_map[customer.name] = customer

        created_entries = 0
        existing_entries = 0

        for days_ago, cust_name, kind, amount_str, note, source_text in ENTRIES_DATA:
            customer = customer_map[cust_name]
            entry_amount = Decimal(amount_str)
            # Use deterministic timestamp anchored to date for exact idempotency matching
            entry_time = (now - timedelta(days=days_ago)).replace(
                hour=10, minute=30, second=0, microsecond=0
            )

            # Check if this exact entry already exists for customer
            entry = LedgerEntry.objects.filter(
                customer=customer,
                kind=kind,
                amount=entry_amount,
                note=note,
                created_at=entry_time,
            ).first()

            if not entry:
                LedgerEntry.objects.create(
                    customer=customer,
                    kind=kind,
                    amount=entry_amount,
                    note=note,
                    source_text=source_text,
                    created_at=entry_time,
                )
                created_entries += 1
            else:
                existing_entries += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[Seed Complete] Customers: {created_customers} created, {existing_customers} existing. "
                f"Ledger Entries: {created_entries} created, {existing_entries} existing."
            )
        )

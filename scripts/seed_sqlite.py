import os
import sqlite3

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH = os.path.join(DATA_DIR, "regguard.db")

def create_schema(cursor):
    cursor.execute("DROP TABLE IF EXISTS transactions;")
    cursor.execute("DROP TABLE IF EXISTS accounts;")
    cursor.execute("DROP TABLE IF EXISTS customers;")

    cursor.execute("""
    CREATE TABLE customers (
        customer_id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        entity_type TEXT CHECK(entity_type IN ('INDIVIDUAL', 'CORPORATE')) NOT NULL,
        dob TEXT,
        bvn TEXT,
        nin TEXT,
        cac_rc_number TEXT,
        nationality TEXT DEFAULT 'NGA',
        risk_rating TEXT CHECK(risk_rating IN ('LOW', 'MEDIUM', 'HIGH')),
        kyc_status TEXT CHECK(kyc_status IN ('VERIFIED', 'TIER_1', 'TIER_3')),
        created_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE accounts (
        account_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL REFERENCES customers(customer_id),
        account_number TEXT UNIQUE NOT NULL,
        account_type TEXT CHECK(account_type IN ('SAVINGS', 'CURRENT', 'CORPORATE')) NOT NULL,
        currency TEXT DEFAULT 'NGN',
        balance REAL NOT NULL,
        status TEXT DEFAULT 'ACTIVE',
        opened_date TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE transactions (
        transaction_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES accounts(account_id),
        transaction_type TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'NGN',
        narration TEXT,
        channel TEXT NOT NULL,
        counterparty_name TEXT,
        counterparty_account TEXT,
        counterparty_bank TEXT,
        timestamp TEXT NOT NULL,
        flag_code TEXT
    );
    """)

def seed_data(cursor):
    # 1. Customers
    customers = [
        # Case A: Emeka Okafor (Structuring case)
        ("CUST-IND-9021", "Emeka Okafor", "INDIVIDUAL", "1985-06-20", "22145567890", "11029384756", None, "NGA", "MEDIUM", "TIER_3", "2020-04-12T08:00:00Z"),
        # Case B: Musa Ibrahim (PEP name match but DOB 1994 vs 1961)
        ("CUST-IND-4412", "Musa Ibrahim", "INDIVIDUAL", "1994-08-12", "22198031201", "88291029384", None, "NGA", "HIGH", "VERIFIED", "2021-02-10T11:15:00Z"),
        # Case C: Kudirat Logistics Ltd (2021 corporate cash limit)
        ("CUST-CORP-1011", "Kudirat Logistics Ltd", "CORPORATE", None, None, None, "RC-892101", "NGA", "LOW", "VERIFIED", "2018-03-10T09:30:00Z"),
        # General background customers
        ("CUST-IND-1001", "Amina Abubakar", "INDIVIDUAL", "1990-11-04", "22233445566", "99001122334", None, "NGA", "LOW", "VERIFIED", "2019-01-15T10:00:00Z"),
        ("CUST-CORP-2002", "Dangote Cement Retail Sub-Agent", "CORPORATE", None, None, None, "RC-112233", "NGA", "LOW", "VERIFIED", "2017-05-20T14:00:00Z"),
        # Challenging Test Cases
        ("CUST-IND-7701", "Alhaji Bashir Hassan", "INDIVIDUAL", "1984-12-05", "22334411223", "77889900112", None, "NGA", "HIGH", "VERIFIED", "2021-08-10T11:00:00Z"),
        ("CUST-CORP-4004", "GreenHorizon Agri-Commodities Ltd", "CORPORATE", None, None, None, "RC-445566", "NGA", "LOW", "VERIFIED", "2020-02-14T09:00:00Z"),
        ("CUST-IND-3305", "Ibrahim D. Suleiman", "INDIVIDUAL", "1998-02-14", "22001144556", "33445566778", None, "NGA", "MEDIUM", "TIER_1", "2021-03-20T14:30:00Z")
    ]
    cursor.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?);", customers)

    # 2. Accounts
    accounts = [
        ("ACC-IND-9021", "CUST-IND-9021", "0123456789", "SAVINGS", "NGN", 5520000.0, "ACTIVE", "2020-04-12"),
        ("ACC-IND-4412", "CUST-IND-4412", "0234567890", "CURRENT", "NGN", 8450000.0, "ACTIVE", "2021-02-10"),
        ("ACC-CORP-1011", "CUST-CORP-1011", "0345678901", "CORPORATE", "NGN", 24000000.0, "ACTIVE", "2018-03-10"),
        ("ACC-IND-1001", "CUST-IND-1001", "0456789012", "SAVINGS", "NGN", 350000.0, "ACTIVE", "2019-01-15"),
        ("ACC-CORP-2002", "CUST-CORP-2002", "0567890123", "CORPORATE", "NGN", 12000000.0, "ACTIVE", "2017-05-20"),
        ("ACC-IND-7701", "CUST-IND-7701", "0678901234", "CURRENT", "NGN", 9400000.0, "ACTIVE", "2021-08-10"),
        ("ACC-CORP-4004", "CUST-CORP-4004", "0789012345", "CORPORATE", "NGN", 45000000.0, "ACTIVE", "2020-02-14"),
        ("ACC-IND-3305", "CUST-IND-3305", "0890123456", "SAVINGS", "NGN", 6820000.0, "ACTIVE", "2021-03-20")
    ]
    cursor.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?);", accounts)

    # 3. Transactions
    transactions = [
        # Case A: Structuring triplet (Total: 5.5M in 36h)
        ("TX-NGA-2023-0101-1", "ACC-IND-9021", "CASH_DEPOSIT", 1900000.0, "NGN", "Cash deposit at Victoria Island Branch", "BRANCH_TELLER", None, None, None, "2023-01-01 10:15:00", None),
        ("TX-NGA-2023-0101-2", "ACC-IND-9021", "CASH_DEPOSIT", 1750000.0, "NGN", "Cash deposit at Ikeja Branch", "BRANCH_TELLER", None, None, None, "2023-01-01 16:30:00", None),
        ("TX-NGA-2023-0101", "ACC-IND-9021", "CASH_DEPOSIT", 1850000.0, "NGN", "Cash deposit at Lekki Phase 1 Branch", "BRANCH_TELLER", None, None, None, "2023-01-02 11:45:00", "RAPID_AGGREGATION_STRUCTURING"),

        # Case B: Flagged Inward Transfer for Musa Ibrahim
        ("TX-NGA-2023-0202", "ACC-IND-4412", "INWARD_TRANSFER", 8200000.0, "NGN", "Contract settlement payment", "NIP_TRANSFER", "Danladi Trading Enterprises", "9011223344", "Zenith Bank", "2023-02-15 09:40:00", "PEP_NAME_MATCH"),

        # Case C: 2021 Corporate Cash Deposit under 2013 rules (7.5M < 10M limit)
        ("TX-NGA-2021-0303", "ACC-CORP-1011", "CASH_DEPOSIT", 7500000.0, "NGN", "Freight proceeds cash deposit", "BRANCH_TELLER", None, None, None, "2021-08-14 11:20:00", "CORPORATE_CASH_THRESHOLD"),

        # Background transactions
        ("TX-BG-001", "ACC-IND-1001", "ATM_WITHDRAWAL", 20000.0, "NGN", "ATM Cash Out Lekki", "ATM", None, None, None, "2023-01-10 14:10:00", None),
        ("TX-BG-002", "ACC-CORP-2002", "INWARD_TRANSFER", 3500000.0, "NGN", "Distribution invoice settlement", "NIP_TRANSFER", "Lafarge Sub-Vendor", "1122334455", "Access Bank", "2023-01-12 16:00:00", None),

        # Corporate Smurfing Triplet for GreenHorizon Agri-Commodities (Total: 11.5M in 25.75h > 10M Corporate limit)
        ("TX-CORP-SMURF-01", "ACC-CORP-4004", "CASH_DEPOSIT", 3800000.0, "NGN", "Cash deposit at Kano Central Branch", "BRANCH_TELLER", None, None, None, "2023-04-10 09:30:00", None),
        ("TX-CORP-SMURF-02", "ACC-CORP-4004", "CASH_DEPOSIT", 4100000.0, "NGN", "Cash deposit at Kaduna South Branch", "BRANCH_TELLER", None, None, None, "2023-04-10 15:45:00", None),
        ("TX-CORP-SMURF-03", "ACC-CORP-4004", "CASH_DEPOSIT", 3600000.0, "NGN", "Cash deposit at Zaria Main Branch", "BRANCH_TELLER", None, None, None, "2023-04-11 11:15:00", "RAPID_AGGREGATION_STRUCTURING"),

        # Critical Sanctions Alias Hit: Bashir Al-Hassan
        ("TX-SANC-HIT-01", "ACC-IND-7701", "INWARD_TRANSFER", 9400000.0, "NGN", "Mining equipment clearing wire", "NIP_TRANSFER", "Sahel Mineral Trading FZE", "1100223344", "Jaiz Bank", "2023-05-18 10:20:00", "SANCTIONS_NAME_ALIAS_MATCH"),

        # Dormant Account Money Mule Velocity Spike
        ("TX-MULE-SPIKE-01", "ACC-IND-3305", "INWARD_TRANSFER", 6800000.0, "NGN", "Peer crowd remittance funds", "NIP_TRANSFER", "Unknown Remitter", "8899001122", "Kuda MFB", "2023-06-02 14:15:00", "DORMANT_ACCOUNT_VELOCITY_SPIKE")
    ]
    cursor.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?);", transactions)

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    create_schema(cursor)
    seed_data(cursor)
    conn.commit()
    conn.close()
    print(f"✓ SQLite database successfully initialized and seeded at: {DB_PATH}")

if __name__ == "__main__":
    main()

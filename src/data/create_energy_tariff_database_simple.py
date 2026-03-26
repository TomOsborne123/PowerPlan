import os

import mysql.connector
from mysql.connector import Error

from src.db import mysql_config

def create_energy_tariff_database_simple():
    """
    Creates a simple proof-of-concept database for energy tariff analysis
    Uses a single denormalized fact table for quick development
    """

    conn = None
    cursor = None
    try:
        # Connect to MySQL server (without specifying a database)
        print("Connecting to MySQL server...")
        cfg = mysql_config()
        # We want to create/drop the target database, so connect without selecting a DB.
        cfg.pop("database", None)
        conn = mysql.connector.connect(**cfg)

        if conn.is_connected():
            print("✓ Connected to MySQL server")
            cursor = conn.cursor()

            # Create database
            print("\nCreating database...")
            target_db = os.environ.get("TARGET_DB_NAME", "energy_tariff")

            cursor.execute(f"DROP DATABASE IF EXISTS {target_db}")
            cursor.execute(f"""
                CREATE DATABASE {target_db}
                CHARACTER SET utf8mb4
                COLLATE utf8mb4_unicode_ci
            """)
            print(f"✓ Database '{target_db}' created")

            # Use the new database
            cursor.execute(f"USE {target_db}")

            # Create single fact table
            print("\nCreating fact table...")
            cursor.execute("""
                CREATE TABLE fact_tariff_search_simple (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    current_supplier_name VARCHAR(100) NOT NULL,
                    pay_method VARCHAR(100) NOT NULL,
                    EV_question VARCHAR(100) NOT NULL,
                    new_supplier_name VARCHAR(100) NOT NULL,
                    tariff_name VARCHAR(150) NOT NULL,
                    tariff_type VARCHAR(50) NOT NULL,
                    fixed_price_length_months INT,
                    is_green BOOLEAN DEFAULT FALSE,
                    region_code VARCHAR(10),
                    region_name VARCHAR(100),
                    dno_name VARCHAR(100),
                    dno_id VARCHAR(20),
                    postcode VARCHAR(10),
                    outward_code VARCHAR(4),
                    latitude DECIMAL(10, 8),
                    longitude DECIMAL(11, 8),
                    fuel_type VARCHAR(20) NOT NULL,
                    search_date DATE NOT NULL,
                    month INT,
                    year INT,
                    annual_electricity_kwh INT,
                    annual_gas_kwh INT,
                    unit_rate DECIMAL(10, 4),
                    standing_charge DECIMAL(10, 4),
                    exit_fee DECIMAL(10, 2) DEFAULT 0.00,
                    annual_cost_current DECIMAL(10, 2),
                    annual_cost_new DECIMAL(10, 2),
                    valid_from DATE,
                    valid_to DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_postcode (postcode),
                    INDEX idx_region (region_code),
                    INDEX idx_supplier (new_supplier_name),
                    INDEX idx_tariff (tariff_name),
                    INDEX idx_fuel_type (fuel_type),
                    INDEX idx_search_date (search_date),
                    INDEX idx_valid_dates (valid_from, valid_to)
                )
            """)
            print("✓ Created fact_tariff_data")

    except Error as e:
        print(f"\n✗ Error: {e}")

    finally:
        if conn is not None and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()
            print("\n✓ MySQL connection closed")


if __name__ == "__main__":
    create_energy_tariff_database_simple()
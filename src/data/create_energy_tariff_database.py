# Import mysql connection library
import mysql.connector
from mysql.connector import Error

def create_energy_tariff_database():
    """
    Creates a star schema database for energy tariff analysis
    """

    try:
        # Connect to MySQL server (without specifying a database)
        print("Connecting to MySQL server...")
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="password"
        )

        if conn.is_connected():
            print("✓ Connected to MySQL server")
            cursor = conn.cursor()

            # Create database
            print("\nCreating database...")
            cursor.execute("DROP DATABASE IF EXISTS energy_tariff")
            cursor.execute("""
                CREATE DATABASE energy_tariff
                CHARACTER SET utf8mb4
                COLLATE utf8mb4_unicode_ci
            """)
            print("✓ Database 'energy_tariff' created")

            # Use the new database
            cursor.execute("USE energy_tariff")

            # Create dimension tables
            print("\nCreating dimension tables...")

            # 1. Supplier Dimension
            cursor.execute("""
                CREATE TABLE dim_supplier (
                    supplier_key INT AUTO_INCREMENT PRIMARY KEY,
                    supplier_id VARCHAR(20) UNIQUE NOT NULL,
                    supplier_name VARCHAR(100) NOT NULL,
                    website_url VARCHAR(255),
                    phone_number VARCHAR(20),
                    is_active BOOLEAN DEFAULT TRUE,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            print("✓ Created dim_supplier")

            # 2. Tariff Dimension
            cursor.execute("""
                CREATE TABLE dim_tariff (
                    tariff_key INT AUTO_INCREMENT PRIMARY KEY,
                    tariff_id VARCHAR(50) UNIQUE NOT NULL,
                    tariff_name VARCHAR(150) NOT NULL,
                    tariff_type VARCHAR(50) NOT NULL,
                    payment_method VARCHAR(50),
                    contract_length_months INT,
                    is_green BOOLEAN DEFAULT FALSE,
                    tariff_description TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            print("✓ Created dim_tariff")

            # 3. Region Dimension
            cursor.execute("""
                CREATE TABLE dim_region (
                    region_key INT AUTO_INCREMENT PRIMARY KEY,
                    region_code VARCHAR(10) UNIQUE NOT NULL,
                    region_name VARCHAR(100) NOT NULL,
                    dno_name VARCHAR(100),
                    dno_id VARCHAR(20),
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            print("✓ Created dim_region")

            # 4. Postcode Dimension
            cursor.execute("""
                CREATE TABLE dim_postcode (
                    postcode_key INT AUTO_INCREMENT PRIMARY KEY,
                    postcode VARCHAR(10) UNIQUE NOT NULL,
                    outward_code VARCHAR(4) NOT NULL,
                    region_key INT NOT NULL,
                    latitude DECIMAL(10, 8),
                    longitude DECIMAL(11, 8),
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (region_key) REFERENCES dim_region(region_key),
                    INDEX idx_postcode (postcode),
                    INDEX idx_outward (outward_code)
                )
            """)
            print("✓ Created dim_postcode")

            # 5. Date Dimension
            cursor.execute("""
                CREATE TABLE dim_date (
                    date_key INT PRIMARY KEY,
                    full_date DATE NOT NULL,
                    day_of_week VARCHAR(10),
                    day_of_month INT,
                    month INT,
                    month_name VARCHAR(10),
                    quarter INT,
                    year INT,
                    is_weekend BOOLEAN,
                    season VARCHAR(10),
                    INDEX idx_full_date (full_date),
                    INDEX idx_year_month (year, month)
                )
            """)
            print("✓ Created dim_date")

            # 6. Fuel Type Dimension
            cursor.execute("""
                CREATE TABLE dim_fuel_type (
                    fuel_type_key INT AUTO_INCREMENT PRIMARY KEY,
                    fuel_type VARCHAR(20) UNIQUE NOT NULL,
                    fuel_description VARCHAR(100)
                )
            """)
            print("✓ Created dim_fuel_type")

            # 7. Consumption Profile Dimension
            cursor.execute("""
                CREATE TABLE dim_consumption_profile (
                    profile_key INT AUTO_INCREMENT PRIMARY KEY,
                    profile_name VARCHAR(50) NOT NULL,
                    annual_electricity_kwh INT,
                    annual_gas_kwh INT,
                    household_type VARCHAR(50),
                    description TEXT
                )
            """)
            print("✓ Created dim_consumption_profile")

            # Create fact table
            print("\nCreating fact table...")
            cursor.execute("""
                CREATE TABLE fact_tariff_search (
                    rate_id INT AUTO_INCREMENT PRIMARY KEY,
                    tariff_key INT NOT NULL,
                    supplier_key INT NOT NULL,
                    region_key INT NOT NULL,
                    date_key INT NOT NULL,
                    fuel_type_key INT NOT NULL,
                    unit_rate DECIMAL(10, 4),
                    standing_charge_day DECIMAL(10, 4),
                    exit_fee DECIMAL(10, 2),
                    annual_cost_low_user DECIMAL(10, 2),
                    annual_cost_medium_user DECIMAL(10, 2),
                    annual_cost_high_user DECIMAL(10, 2),
                    annual_cost_user DECIMAL(10, 2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (tariff_key) REFERENCES dim_tariff(tariff_key),
                    FOREIGN KEY (supplier_key) REFERENCES dim_supplier(supplier_key),
                    FOREIGN KEY (region_key) REFERENCES dim_region(region_key),
                    FOREIGN KEY (date_key) REFERENCES dim_date(date_key),
                    FOREIGN KEY (fuel_type_key) REFERENCES dim_fuel_type(fuel_type_key),
                    INDEX idx_tariff (tariff_key),
                    INDEX idx_supplier (supplier_key),
                    INDEX idx_region (region_key),
                    INDEX idx_date (date_key),
                    INDEX idx_fuel (fuel_type_key)
                )
            """)
            print("✓ Created fact_tariff_search")

    except Error as e:
        print(f"\n✗ Error: {e}")

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            print("\n✓ MySQL connection closed")


if __name__ == "__main__":
    create_energy_tariff_database()
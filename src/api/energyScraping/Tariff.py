"""
Created 02-03-26
@author: Tom Osborne
"""

import mysql.connector
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

@dataclass
class Tariff:
    # Tariff details
    new_supplier_name: str
    tariff_name: str
    tariff_type: str
    pay_method: str
    fixed_price_length_months: int
    is_green: bool

    # Location details
    region_code: str
    region_name: str
    dno_name: str
    dno_id: str
    postcode: str
    outward_code: str
    latitude: float
    longitude: float

    fuel_type: str

    # Search details
    search_date: datetime
    month: int
    year: int

    # Cost details
    annual_electricity_kwh: int
    annual_gas_kwh: int
    unit_rate: float
    standing_charge_day: float
    exit_fee: float
    annual_cost_current: float
    annual_cost_new: float
    valid_from: datetime
    valid_to: datetime
    created_at: datetime
    last_updated: datetime

    @contextmanager
    def _get_db_connection(self):
        """Context manager for database connections"""
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="password",  # Consider using environment variables
            database="energy_tariff"
        )
        try:
            yield conn
        finally:
            conn.close()

    def save(self, current_supplier: str, pay_method: str, EV_question: str):
        """Save tariff to database using parameterized query
        
        Args:
            current_supplier: Current energy supplier name
            pay_method: Payment method (e.g., 'monthly_direct_debit')
            EV_question: EV question answer - 'Yes', 'No', or 'No but interested'
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()

            query = """
            INSERT INTO fact_tariff_search_simple (
                current_supplier_name, pay_method, EV_question, new_supplier_name, 
                tariff_name, tariff_type, pay_method, fixed_price_length_months, 
                is_green, region_code, region_name, dno_name, dno_id, postcode, 
                outward_code, latitude, longitude, fuel_type, search_date, month, 
                year, annual_electricity_kwh, annual_gas_kwh, unit_rate, 
                standing_charge, exit_fee, annual_cost_current, annual_cost_new, 
                valid_from, valid_to, created_at, last_updated
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """

            values = (
                current_supplier,
                pay_method,
                EV_question,
                self.new_supplier_name,
                self.tariff_name,
                self.tariff_type,
                self.pay_method,
                self.fixed_price_length_months,
                self.is_green,
                self.region_code,
                self.region_name,
                self.dno_name,
                self.dno_id,
                self.postcode,
                self.outward_code,
                self.latitude,
                self.longitude,
                self.fuel_type,
                self.search_date,
                self.month,
                self.year,
                self.annual_electricity_kwh,
                self.annual_gas_kwh,
                self.unit_rate,
                self.standing_charge_day,
                self.exit_fee,
                self.annual_cost_current,
                self.annual_cost_new,
                self.valid_from,
                self.valid_to,
                self.created_at,
                self.last_updated
            )

            try:
                cursor.execute(query, values)
                conn.commit()
                return cursor.lastrowid
            except mysql.connector.Error as err:
                conn.rollback()
                raise Exception(f"Database error: {err}")
            finally:
                cursor.close()
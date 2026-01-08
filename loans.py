from dataclasses import dataclass
from typing import Optional, List

from supabase import Client
from rich.console import Console
import questionary

@dataclass
class Loan:
  id: int
  name: str
  interest_rate: float
  apr_rate: float
  down_payment_rate: float
  years: int
  mip_upfront_rate: float
  mip_annual_rate: float
  upfront_discounts: float
  preapproval_link: str
  preapproved_amount: int
  issued_date: str
  expiration_date: str
  lender_fees: float
  loan_type: str

class LoansProvider:
    def __init__(self, supabase_client: Client, console: Console):
        self.supabase = supabase_client
        self.console = console

    def get_loans(self) -> Optional[List[Loan]]:
        try:
            response = self.supabase.table("loans").select("*").limit(10000).execute()
            if not response:
                self.console.print("[red]Loans not found[/red]")
                return None
            return [Loan(**loan_dict) for loan_dict in response.data]
        except Exception as e:
            self.console.print(f"[red]Error getting loans: {str(e)}[/red]")
            return None

    def get_loan_by_id(self, id) -> Optional[Loan]:
        try:
            response = (
                self.supabase.table("loans")
                .select("*")
                .eq("id", id)
                .limit(1)
                .single()
                .execute()
            )
            if not response:
                self.console.print(f"[red]Loan {id} not found[/red]")
                return None
            return Loan(**response.data)
        except Exception as e:
            self.console.print(f"[red]Error getting loan {id}: {str(e)}[/red]")
            return None

    def collect_loan_details(self) -> Loan:
        name = questionary.text(
            "Loan name/type (e.g. 'FHA', 'Conventional', etc.)"
        ).ask()

        interest_rate_pct = questionary.text(
            "Interest rate (%)", validate=lambda x: x.replace(".", "").isdigit()
        ).ask()
        interest_rate = float(interest_rate_pct) / 100

        apr_rate_pct = questionary.text(
            "APR rate(%)", validate=lambda x: x.replace(".", "").isdigit()
        ).ask()
        apr_rate = float(apr_rate_pct) / 100

        down_payment_pct = questionary.text(
            "Down payment rate (%)", validate=lambda x: x.replace(".", "").isdigit()
        ).ask()
        down_payment_rate = float(down_payment_pct) / 100

        years = questionary.text(
            "Loan term (years)", validate=lambda x: x.isdigit()
        ).ask()

        mip_upfront_pct = questionary.text(
            "MIP upfront rate (%) - enter 0 if none",
            validate=lambda x: x.replace(".", "").isdigit(),
        ).ask()
        mip_upfront_rate = float(mip_upfront_pct) / 100

        mip_annual_pct = questionary.text(
            "MIP annual rate (%) - enter 0 if none",
            validate=lambda x: x.replace(".", "").isdigit(),
        ).ask()
        mip_annual_rate = float(mip_annual_pct) / 100

        upfront_discounts = questionary.text(
            "Upfront discounts ($) - enter 0 if none",
            validate=lambda x: x.replace(".", "").isdigit(),
        ).ask()

        lender_fees = questionary.text(
            "Lender fees ($) - enter 0 if none",
            validate=lambda x: x.replace(".", "").isdigit(),
        ).ask()

        preapproval_link = questionary.text("Preapproval link (URL) - optional").ask()
        preapproved_amount = questionary.text("Preapproved amount ($)", validate=lambda x: x.replace(",", "").isdigit()).ask()
        issued_date = questionary.text("Issued date (YYYY-MM-DD)").ask()
        expiration_date = questionary.text("Expiration date (YYYY-MM-DD)").ask()
        loan_type = questionary.select("Type of loan", choices=["CONVENTIONAL", "FHA"]).ask()

        return Loan(
            id=0,  # Will be set by database
            name=name.strip(),
            interest_rate=interest_rate,
            apr_rate=apr_rate,
            down_payment_rate=down_payment_rate,
            years=int(years),
            mip_upfront_rate=mip_upfront_rate,
            mip_annual_rate=mip_annual_rate,
            lender_fees=float(lender_fees),
            upfront_discounts=float(upfront_discounts),
            preapproval_link=preapproval_link.strip(),
            preapproved_amount=int(preapproved_amount.replace(",", "")),
            issued_date=issued_date.strip() if issued_date != "" else None,
            expiration_date=expiration_date.strip() if expiration_date != "" else None,
            loan_type=loan_type,
        )

    def add_loan(self, loan_data: Loan) -> bool:
        try:
            loan_dict = {
                "name": loan_data.name,
                "interest_rate": loan_data.interest_rate,
                "apr_rate": loan_data.apr_rate,
                "down_payment_rate": loan_data.down_payment_rate,
                "years": loan_data.years,
                "mip_upfront_rate": loan_data.mip_upfront_rate,
                "mip_annual_rate": loan_data.mip_annual_rate,
                "lender_fees": loan_data.lender_fees,
                "upfront_discounts": loan_data.upfront_discounts,
                "preapproval_link": loan_data.preapproval_link,
                "preapproved_amount": loan_data.preapproved_amount,
                "issued_date": loan_data.issued_date,
                "expiration_date": loan_data.expiration_date,
            }

            response = self.supabase.table("loans").insert(loan_dict).execute()

            if hasattr(response, "data") and response.data:
                self.console.print(
                    f"[green]Loan '{loan_data.name}' added successfully![/green]"
                )
                return True
            else:
                self.console.print("[red]Failed to add loan - no data returned[/red]")
                return False

        except Exception as e:
            self.console.print(f"[red]Error adding loan: {str(e)}[/red]")
            return False
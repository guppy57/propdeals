from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from supabase import Client
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import questionary

@dataclass
class Loan:
  id: int
  name: str
  interest_rate: float
  down_payment_rate: float
  years: int
  mip_upfront_rate: float
  mip_annual_rate: float
  upfront_discounts: float
  preapproval_link: str
  preapproved_amount: int
  issued_date: str
  expiration_date: str

class LoansProvider:
  def __init__(self, supabase_client: Client, console: Console):
    self.supabase = supabase_client
    self.console = console
  
  def get_loans(self) -> Optional[List[Loan]]:
    try:
      response = self.supabase.table('loans').select('*').execute()
      if not response:
        self.console.print("[red]Loans not found[/red]")
        return None
      return [Loan(**loan_dict) for loan_dict in response.data]
    except Exception as e:
      self.console.print(f"[red]Error getting loans: {str(e)}[/red]")
      return None

  def display_loans(self):
    loans = self.get_loans()

    if not loans:
      self.console.print("[red]Loans could not be fetched![/red]")
      return
    
    table = Table(title="Available Loans", show_header=True, header_style="bold magenta")
    
    # Add columns (excluding id, preapproval_link, issued_date as requested)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Interest Rate", justify="right", style="green")
    table.add_column("Down Payment", justify="right", style="yellow")
    table.add_column("Term (Years)", justify="right", style="blue")
    table.add_column("MIP Upfront", justify="right", style="orange3")
    table.add_column("MIP Annual", justify="right", style="orange3")
    table.add_column("Upfront Discounts", justify="right", style="red")
    table.add_column("Preapproved Amount", justify="right", style="purple")
    table.add_column("Expiration Date", style="white")
    
    # Add rows for each loan
    for loan in loans:
      preapproved_amount = loan.preapproved_amount or 0.0

      table.add_row(
        str(loan.name),
        f"{loan.interest_rate * 100:.2f}%",
        f"{loan.down_payment_rate * 100:.1f}%",
        str(loan.years),
        f"{loan.mip_upfront_rate * 100:.2f}%",
        f"{loan.mip_annual_rate * 100:.2f}%",
        f"${loan.upfront_discounts:,.2f}",
        f"${preapproved_amount:,}",
        str(loan.expiration_date)
      )
    
    self.console.print(table)

  def collect_loan_details(self) -> Loan:
    name = questionary.text("Loan name/type (e.g. 'FHA', 'Conventional', etc.)").ask()
    
    interest_rate_pct = questionary.text("Interest rate (%)", validate=lambda x: x.replace('.', '').isdigit()).ask()
    interest_rate = float(interest_rate_pct) / 100
    
    down_payment_pct = questionary.text("Down payment rate (%)", validate=lambda x: x.replace('.', '').isdigit()).ask()
    down_payment_rate = float(down_payment_pct) / 100
    
    years = questionary.text("Loan term (years)", validate=lambda x: x.isdigit()).ask()
    
    mip_upfront_pct = questionary.text("MIP upfront rate (%) - enter 0 if none", validate=lambda x: x.replace('.', '').isdigit()).ask()
    mip_upfront_rate = float(mip_upfront_pct) / 100
    
    mip_annual_pct = questionary.text("MIP annual rate (%) - enter 0 if none", validate=lambda x: x.replace('.', '').isdigit()).ask()
    mip_annual_rate = float(mip_annual_pct) / 100
    
    upfront_discounts = questionary.text("Upfront discounts ($) - enter 0 if none", validate=lambda x: x.replace('.', '').isdigit()).ask()
    
    preapproval_link = questionary.text("Preapproval link (URL) - optional").ask()
    
    preapproved_amount = questionary.text("Preapproved amount ($)", validate=lambda x: x.replace(',', '').isdigit()).ask()
    
    issued_date = questionary.text("Issued date (YYYY-MM-DD)").ask()
    
    expiration_date = questionary.text("Expiration date (YYYY-MM-DD)").ask()
    
    return Loan(
      id=0,  # Will be set by database
      name=name.strip(),
      interest_rate=interest_rate,
      down_payment_rate=down_payment_rate,
      years=int(years),
      mip_upfront_rate=mip_upfront_rate,
      mip_annual_rate=mip_annual_rate,
      upfront_discounts=float(upfront_discounts),
      preapproval_link=preapproval_link.strip(),
      preapproved_amount=int(preapproved_amount.replace(',', '')),
      issued_date=issued_date.strip(),
      expiration_date=expiration_date.strip()
    )

  def add_loan(self, loan_data: Loan) -> bool:
    try:
      loan_dict = {
        "name": loan_data.name,
        "interest_rate": loan_data.interest_rate,
        "down_payment_rate": loan_data.down_payment_rate,
        "years": loan_data.years,
        "mip_upfront_rate": loan_data.mip_upfront_rate,
        "mip_annual_rate": loan_data.mip_annual_rate,
        "upfront_discounts": loan_data.upfront_discounts,
        "preapproval_link": loan_data.preapproval_link,
        "preapproved_amount": loan_data.preapproved_amount,
        "issued_date": loan_data.issued_date,
        "expiration_date": loan_data.expiration_date
      }
      
      response = self.supabase.table('loans').insert(loan_dict).execute()
      
      if hasattr(response, 'data') and response.data:
        self.console.print(f"[green]Loan '{loan_data.name}' added successfully![/green]")
        return True
      else:
        self.console.print("[red]Failed to add loan - no data returned[/red]")
        return False
        
    except Exception as e:
      self.console.print(f"[red]Error adding loan: {str(e)}[/red]")
      return False
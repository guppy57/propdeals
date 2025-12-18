"""
Student Loan Payoff vs. Investment Analysis
============================================
Compares two strategies over a 40-year horizon:
1. Aggressive: $1500/month all to debt (avalanche), then all to market
2. Balanced: $400/month to debt (avalanche), $1100/month to market

Uses daily interest accrual and 7% annual stock market return.
Includes tax modeling, inflation adjustment, and sensitivity analysis.
"""

from dataclasses import dataclass
from typing import List, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.console import Group

# Create console instance for Rich output
console = Console()


@dataclass
class Loan:
    """Represents a student loan with daily accrual."""

    name: str
    balance: float
    annual_rate: float  # As decimal (e.g., 0.0525 for 5.25%)
    min_payment: float

    @property
    def daily_rate(self) -> float:
        return self.annual_rate / 365

    def accrue_daily_interest(self, days: int = 30) -> float:
        """Accrue interest for given number of days using daily compounding. Returns interest added."""
        old_balance = self.balance
        self.balance = self.balance * ((1 + self.daily_rate) ** days)
        interest = self.balance - old_balance
        return interest

    def make_payment(self, amount: float) -> float:
        """Make a payment. Returns actual amount paid (may be less if balance is lower)."""
        actual_payment = min(amount, self.balance)
        self.balance -= actual_payment
        return actual_payment

    def is_paid_off(self) -> bool:
        return self.balance <= 0.01  # Small threshold for floating point


def get_initial_loans() -> List[Loan]:
    """Returns Guppy's 4 student loans from the screenshot."""
    return [
        Loan(name="AA", balance=5230.56, annual_rate=0.0250, min_payment=55.00),
        Loan(name="AB", balance=5318.72, annual_rate=0.0348, min_payment=58.30),
        Loan(name="AC", balance=10119.74, annual_rate=0.0474, min_payment=116.91),
        Loan(name="AD", balance=6572.16, annual_rate=0.0525, min_payment=87.29),
    ]


def simulate_month(
    loans: List[Loan],
    monthly_allocation: float,
    investment_balance: float,
    retirement_balance: float,
    monthly_investment: float,
    annual_market_return: float = 0.07,
    capital_gains_tax_rate: float = 0.15,
    expense_ratio: float = 0.001,
    retirement_contribution: float = 0.0,
    employer_match_rate: float = 0.0,
    use_roth: bool = False,
) -> tuple:
    """
    Simulate one month of debt payments and investment growth.

    Uses avalanche method: pay minimums first, then extra to highest rate.
    Applies capital gains tax on investment returns and expense ratio fees.
    Supports 401(k) with employer match and Roth IRA.

    Returns: (extra_to_invest, new_investment_balance, new_retirement_balance,
              interest_paid, investment_gains, retirement_gains)
    """
    # Step 1: Accrue daily interest on all loans (assume 30 days/month)
    total_interest_accrued = 0
    for loan in loans:
        if not loan.is_paid_off():
            total_interest_accrued += loan.accrue_daily_interest(days=30)

    # Step 2: Pay minimums on all active loans
    remaining = monthly_allocation
    for loan in loans:
        if not loan.is_paid_off():
            payment = loan.make_payment(loan.min_payment)
            remaining -= payment

    # Step 3: Apply extra to highest interest rate loan (avalanche)
    # Sort active loans by interest rate descending
    active_loans = [l for l in loans if not l.is_paid_off()]
    active_loans.sort(key=lambda x: x.annual_rate, reverse=True)

    for loan in active_loans:
        if remaining <= 0:
            break
        payment = loan.make_payment(remaining)
        remaining -= payment

    # Step 4: Any remaining allocation goes to investments
    extra_to_invest = max(0, remaining)
    total_to_invest = monthly_investment + extra_to_invest

    # Step 5: Handle retirement contributions (401k/IRA)
    # Retirement contribution is separate from regular investment
    total_retirement_contribution = retirement_contribution

    # Add employer match
    employer_match = retirement_contribution * employer_match_rate

    # Total going into retirement account
    total_retirement_deposit = total_retirement_contribution + employer_match

    # Step 6: Grow retirement balance (tax-free growth for Roth, tax-deferred for 401k)
    monthly_expense_ratio = expense_ratio / 12
    gross_monthly_rate = (1 + annual_market_return) ** (1 / 12) - 1
    net_monthly_rate = (1 + gross_monthly_rate) * (1 - monthly_expense_ratio) - 1

    # Retirement account grows without capital gains tax (either tax-deferred or Roth)
    retirement_gains = retirement_balance * net_monthly_rate
    retirement_balance = retirement_balance + retirement_gains + total_retirement_deposit

    # Step 7: Grow taxable investment balance (no tax on unrealized gains)
    # Calculate investment gains before tax
    investment_gains = investment_balance * net_monthly_rate

    # Update taxable investment balance (no capital gains tax until liquidation)
    investment_balance = investment_balance + investment_gains + total_to_invest

    return (
        extra_to_invest,
        investment_balance,
        retirement_balance,
        total_interest_accrued,
        investment_gains,
        retirement_gains,
    )


def run_simulation(
    monthly_debt_allocation: float,
    monthly_investment: float,
    total_months: int = 480,
    annual_market_return: float = 0.07,
    capital_gains_tax_rate: float = 0.15,
    expense_ratio: float = 0.001,
    inflation_rate: float = 0.025,
    marginal_tax_rate: float = 0.22,
    retirement_contribution: float = 0.0,
    employer_match_rate: float = 0.0,
    use_roth: bool = False,
    retirement_withdrawal_tax_rate: float = 0.12,
) -> Dict:
    """
    Run full simulation for a given strategy.

    Args:
        monthly_debt_allocation: Fixed monthly amount for debt payments
        monthly_investment: Fixed monthly amount for taxable investments
        total_months: Simulation duration (480 = 40 years)
        annual_market_return: Expected annual market return
        capital_gains_tax_rate: Tax rate on investment gains
        expense_ratio: Annual expense ratio for investments (e.g., 0.001 = 0.1%)
        inflation_rate: Annual inflation rate (e.g., 0.025 = 2.5%)
        marginal_tax_rate: Tax rate for student loan interest deduction benefit (during working years)
        retirement_contribution: Monthly contribution to 401(k)/IRA
        employer_match_rate: Employer match as % of contribution (e.g., 0.5 = 50%)
        use_roth: True for Roth IRA (after-tax), False for traditional 401(k) (pre-tax)
        retirement_withdrawal_tax_rate: Tax rate on traditional 401(k) withdrawals in retirement (typically lower than working years)

    Returns:
        Dictionary with monthly tracking data
    """
    loans = get_initial_loans()
    investment_balance = 0.0
    retirement_balance = 0.0

    # Tracking
    history = {
        "month": [],
        "total_debt": [],
        "investment_balance": [],
        "retirement_balance": [],
        "net_worth": [],  # taxable investments + retirement - debt
        "debt_by_loan": {loan.name: [] for loan in loans},
        "cumulative_interest_paid": [],
        "cumulative_invested": [],
        "cumulative_retirement_contributed": [],
        "cumulative_employer_match": [],
        "monthly_to_investments": [],
        "cumulative_investment_gains": [],
        "cumulative_retirement_gains": [],
        "cumulative_loan_interest_deduction_value": [],
        "cumulative_pretax_savings": [],
    }

    cumulative_interest = 0
    cumulative_invested = 0
    cumulative_retirement_contributed = 0
    cumulative_employer_match = 0
    cumulative_investment_gains = 0
    cumulative_retirement_gains = 0
    cumulative_loan_interest_deduction = 0
    cumulative_pretax_savings = 0
    all_debt_paid_month = None

    # Track student loan interest deduction per year
    current_year = -1
    year_interest_paid = 0
    year_deduction_used = 0

    for month in range(1, total_months + 1):
        # Calculate current totals before this month's actions
        total_debt = sum(l.balance for l in loans)

        # Check if all debt is paid off
        all_paid = all(l.is_paid_off() for l in loans)

        if all_paid:
            if all_debt_paid_month is None:
                all_debt_paid_month = month - 1
            # All debt paid: full allocation goes to investments
            # Apply fees and taxes even after debt is paid off
            monthly_expense_ratio = expense_ratio / 12
            gross_monthly_rate = (1 + annual_market_return) ** (1 / 12) - 1
            net_monthly_rate = (1 + gross_monthly_rate) * (1 - monthly_expense_ratio) - 1

            # Grow retirement account
            ret_gains = retirement_balance * net_monthly_rate
            employer_match = retirement_contribution * employer_match_rate
            retirement_balance = retirement_balance + ret_gains + retirement_contribution + employer_match

            cumulative_retirement_contributed += retirement_contribution
            cumulative_employer_match += employer_match
            cumulative_retirement_gains += ret_gains

            # Track pre-tax savings (if traditional 401k)
            if not use_roth:
                cumulative_pretax_savings += retirement_contribution * marginal_tax_rate

            # Calculate gains on taxable account (no tax on unrealized gains)
            investment_gains = investment_balance * net_monthly_rate

            total_contribution = monthly_debt_allocation + monthly_investment
            investment_balance = investment_balance + investment_gains + total_contribution

            cumulative_invested += total_contribution
            cumulative_investment_gains += investment_gains
            monthly_invested = total_contribution
            interest_this_month = 0
        else:
            # Still have debt
            (
                extra,
                investment_balance,
                retirement_balance,
                interest,
                gains,
                ret_gains,
            ) = simulate_month(
                loans,
                monthly_debt_allocation,
                investment_balance,
                retirement_balance,
                monthly_investment,
                annual_market_return,
                capital_gains_tax_rate,
                expense_ratio,
                retirement_contribution,
                employer_match_rate,
                use_roth,
            )

            # Track retirement metrics
            employer_match_this_month = retirement_contribution * employer_match_rate
            cumulative_retirement_contributed += retirement_contribution
            cumulative_employer_match += employer_match_this_month
            cumulative_retirement_gains += ret_gains

            # Track pre-tax savings (if traditional 401k)
            if not use_roth:
                cumulative_pretax_savings += retirement_contribution * marginal_tax_rate

            cumulative_interest += interest
            monthly_invested = monthly_investment + extra
            cumulative_invested += monthly_invested
            cumulative_investment_gains += gains
            interest_this_month = interest

        # Calculate student loan interest deduction value (capped at $2,500/year)
        year = (month - 1) // 12

        # Reset year tracking if new calendar year
        if year != current_year:
            current_year = year
            year_interest_paid = 0
            year_deduction_used = 0

        # Add this month's interest to year total
        year_interest_paid += interest_this_month

        # Calculate deductible interest for this month (respecting annual cap)
        annual_deduction_cap = 2500
        remaining_deduction = annual_deduction_cap - year_deduction_used

        if interest_this_month > 0 and remaining_deduction > 0:
            deductible_interest = min(interest_this_month, remaining_deduction)
            tax_benefit = deductible_interest * marginal_tax_rate
            cumulative_loan_interest_deduction += tax_benefit
            year_deduction_used += deductible_interest

        # Record state after this month
        total_debt = sum(loan.balance for loan in loans)
        total_net_worth = investment_balance + retirement_balance - total_debt
        history["month"].append(month)
        history["total_debt"].append(total_debt)
        history["investment_balance"].append(investment_balance)
        history["retirement_balance"].append(retirement_balance)
        history["net_worth"].append(total_net_worth)
        history["cumulative_interest_paid"].append(cumulative_interest)
        history["cumulative_invested"].append(cumulative_invested)
        history["cumulative_retirement_contributed"].append(
            cumulative_retirement_contributed
        )
        history["cumulative_employer_match"].append(cumulative_employer_match)
        history["monthly_to_investments"].append(monthly_invested)
        history["cumulative_investment_gains"].append(cumulative_investment_gains)
        history["cumulative_retirement_gains"].append(cumulative_retirement_gains)
        history["cumulative_loan_interest_deduction_value"].append(
            cumulative_loan_interest_deduction
        )
        history["cumulative_pretax_savings"].append(cumulative_pretax_savings)

        for loan in loans:
            history["debt_by_loan"][loan.name].append(loan.balance)

    # Apply inflation adjustment to final values
    total_years = total_months // 12
    inflation_factor = (1 + inflation_rate) ** total_years

    # Calculate capital gains tax at liquidation (only on taxable account)
    cost_basis = cumulative_invested
    capital_gains = investment_balance - cost_basis
    capital_gains_tax = capital_gains * capital_gains_tax_rate
    investment_after_tax = investment_balance - capital_gains_tax

    # Calculate total account values
    total_account_value = investment_balance + retirement_balance

    # For traditional 401k, account for withdrawal taxes
    retirement_after_tax = retirement_balance
    if not use_roth:
        # Traditional 401k: pay taxes on withdrawal (typically at lower rate in retirement)
        retirement_after_tax = retirement_balance * (1 - retirement_withdrawal_tax_rate)

    total_account_value_after_tax = investment_after_tax + retirement_after_tax

    history["debt_payoff_month"] = all_debt_paid_month
    history["final_investment"] = investment_balance
    history["final_investment_real"] = investment_balance / inflation_factor
    history["final_investment_after_tax"] = investment_after_tax
    history["final_investment_after_tax_real"] = investment_after_tax / inflation_factor
    history["final_retirement"] = retirement_balance
    history["final_retirement_real"] = retirement_balance / inflation_factor
    history["final_retirement_after_tax"] = retirement_after_tax
    history["final_retirement_after_tax_real"] = retirement_after_tax / inflation_factor
    history["final_net_worth"] = total_account_value
    history["final_net_worth_real"] = total_account_value / inflation_factor
    history["final_net_worth_after_tax"] = total_account_value_after_tax
    history["final_net_worth_after_tax_real"] = (
        total_account_value_after_tax / inflation_factor
    )
    history["total_interest_paid"] = cumulative_interest
    history["total_investment_gains"] = cumulative_investment_gains
    history["total_retirement_gains"] = cumulative_retirement_gains
    history["cost_basis"] = cost_basis
    history["capital_gains"] = capital_gains
    history["capital_gains_tax"] = capital_gains_tax
    history["total_loan_interest_deduction_value"] = cumulative_loan_interest_deduction
    history["total_pretax_savings"] = cumulative_pretax_savings
    history["total_employer_match"] = cumulative_employer_match
    history["inflation_factor"] = inflation_factor
    history["use_roth"] = use_roth

    return history


def format_currency(amount: float) -> str:
    """Format number as currency."""
    return f"${amount:,.2f}"


def months_to_years_months(months: int) -> str:
    """Convert months to years and months string."""
    years = months // 12
    remaining_months = months % 12
    if years == 0:
        return f"{remaining_months} months"
    elif remaining_months == 0:
        return f"{years} years"
    else:
        return f"{years} years, {remaining_months} months"


def print_summary(aggressive: Dict, balanced: Dict, config: Dict = None):
    """Print comparison summary of both strategies using Rich tables."""
    console.print()

    # Starting Conditions Panel
    loans = get_initial_loans()
    total_debt = sum(loan.balance for loan in loans)
    total_min = sum(loan.min_payment for loan in loans)

    conditions_text = f"[cyan]Total Debt:[/cyan] {format_currency(total_debt)}\n"
    conditions_text += f"[cyan]Total Minimum Payment:[/cyan] {format_currency(total_min)}/month\n"
    conditions_text += f"[cyan]Monthly Budget:[/cyan] {format_currency(1500)}\n"

    if config:
        years = config.get("total_months", 480) // 12
        conditions_text += f"[cyan]Time Horizon:[/cyan] {years} years\n"
        conditions_text += f"[cyan]Market Return:[/cyan] {config.get('annual_market_return', 0.07) * 100:.1f}% annually\n"
        conditions_text += f"[cyan]Capital Gains Tax:[/cyan] {config.get('capital_gains_tax_rate', 0.15) * 100:.0f}%\n"
        conditions_text += f"[cyan]Expense Ratio:[/cyan] {config.get('expense_ratio', 0.001) * 100:.2f}%\n"
        conditions_text += f"[cyan]Inflation Rate:[/cyan] {config.get('inflation_rate', 0.025) * 100:.1f}%\n"
        conditions_text += f"[cyan]Marginal Tax Rate:[/cyan] {config.get('marginal_tax_rate', 0.22) * 100:.0f}%"

    console.print(Panel(conditions_text, title="[bold magenta]📊 STARTING CONDITIONS[/bold magenta]", border_style="cyan"))

    # Strategy Comparison Table
    table = Table(title="Strategy Comparison (40-Year Analysis)", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", no_wrap=False)
    table.add_column("Aggressive", justify="right", style="green")
    table.add_column("Balanced", justify="right", style="blue")
    table.add_column("Difference", justify="right")

    # Add strategy descriptions
    table.add_row(
        "[bold]Strategy Description[/bold]",
        "$1,500 → debt then brokerage",
        "$377 → debt, $1,123 → brokerage",
        ""
    )
    table.add_section()

    # Debt payoff metrics
    table.add_row(
        "⏱️ Debt Payoff Time",
        months_to_years_months(aggressive['debt_payoff_month']),
        months_to_years_months(balanced['debt_payoff_month']),
        f"[red]{months_to_years_months(balanced['debt_payoff_month'] - aggressive['debt_payoff_month'])} longer[/red]"
    )

    table.add_row(
        "💰 Total Interest Paid",
        format_currency(aggressive['total_interest_paid']),
        format_currency(balanced['total_interest_paid']),
        f"[red]+{format_currency(balanced['total_interest_paid'] - aggressive['total_interest_paid'])}[/red]"
    )

    table.add_row(
        "💸 Loan Interest Tax Benefit",
        format_currency(aggressive['total_loan_interest_deduction_value']),
        format_currency(balanced['total_loan_interest_deduction_value']),
        f"[green]+{format_currency(balanced['total_loan_interest_deduction_value'] - aggressive['total_loan_interest_deduction_value'])}[/green]"
    )

    table.add_section()

    # Investment metrics
    table.add_row(
        "📈 Final Investment (Real)",
        format_currency(aggressive['final_investment_real']),
        format_currency(balanced['final_investment_real']),
        format_currency(balanced['final_investment_real'] - aggressive['final_investment_real'])
    )

    table.add_row(
        "📊 Total Investment Gains",
        format_currency(aggressive['total_investment_gains']),
        format_currency(balanced['total_investment_gains']),
        format_currency(balanced['total_investment_gains'] - aggressive['total_investment_gains'])
    )

    table.add_row(
        "💵 Capital Gains Tax (at liquidation)",
        format_currency(aggressive['capital_gains_tax']),
        format_currency(balanced['capital_gains_tax']),
        f"[red]+{format_currency(balanced['capital_gains_tax'] - aggressive['capital_gains_tax'])}[/red]"
    )

    table.add_section()

    # Final results - Nominal dollars
    diff_nominal = aggressive["final_net_worth_after_tax"] - balanced["final_net_worth_after_tax"]
    nominal_winner_style = "green" if diff_nominal > 0 else "blue"

    table.add_row(
        "[bold]💰 Final Net Worth (Nominal)[/bold]",
        f"[bold]{format_currency(aggressive['final_net_worth_after_tax'])}[/bold]",
        f"[bold]{format_currency(balanced['final_net_worth_after_tax'])}[/bold]",
        f"[{nominal_winner_style}][bold]{format_currency(abs(diff_nominal))}[/bold][/{nominal_winner_style}]"
    )

    # Final results - Real dollars (inflation-adjusted)
    diff_after_tax = aggressive["final_net_worth_after_tax_real"] - balanced["final_net_worth_after_tax_real"]
    winner_style = "green" if diff_after_tax > 0 else "blue"
    winner_name = "Aggressive" if diff_after_tax > 0 else "Balanced"

    table.add_row(
        "[bold]🏆 Final Net Worth (Real)[/bold]",
        f"[bold]{format_currency(aggressive['final_net_worth_after_tax_real'])}[/bold]",
        f"[bold]{format_currency(balanced['final_net_worth_after_tax_real'])}[/bold]",
        f"[{winner_style}][bold]{format_currency(abs(diff_after_tax))}[/bold][/{winner_style}]"
    )

    console.print(table)

    # Winner Panel
    winner_text = f"[bold {winner_style}]{winner_name.upper()} STRATEGY WINS[/bold {winner_style}]\n\n"
    winner_text += f"Advantage: {format_currency(abs(diff_after_tax))} ({abs(diff_after_tax / balanced['final_net_worth_after_tax_real'] * 100):.2f}%)\n\n"

    # Calculate crossover point
    crossover_text = ""
    for i, month in enumerate(aggressive["month"]):
        if balanced["net_worth"][i] > aggressive["net_worth"][i]:
            crossover_month = month
            crossover_text = f"📍 Balanced overtakes Aggressive at month {crossover_month} ({months_to_years_months(crossover_month)})"
            break
    else:
        crossover_text = "📍 Aggressive stays ahead for entire 40-year period"

    winner_text += f"[dim]{crossover_text}[/dim]"

    console.print(Panel(winner_text, title="[bold]🎯 WINNER[/bold]", border_style=winner_style))
    console.print()

def sensitivity_analysis(
    market_returns: List[float] = None,
    config: Dict = None,
):
    """Run sensitivity analysis on different market return assumptions."""
    if market_returns is None:
        market_returns = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10]

    if config is None:
        config = {}

    table = Table(title="📊 Sensitivity Analysis: Market Return Impact", show_header=True, header_style="bold magenta")
    table.add_column("Return", justify="center", style="cyan")
    table.add_column("Aggressive (Real)", justify="right", style="green")
    table.add_column("Balanced (Real)", justify="right", style="blue")
    table.add_column("Winner", justify="center")
    table.add_column("Difference", justify="right")

    results = []
    for rate in market_returns:
        aggressive = run_simulation(
            1500,
            0,
            total_months=config.get("total_months", 480),
            annual_market_return=rate,
            capital_gains_tax_rate=config.get("capital_gains_tax_rate", 0.15),
            expense_ratio=config.get("expense_ratio", 0.001),
            inflation_rate=config.get("inflation_rate", 0.025),
            marginal_tax_rate=config.get("marginal_tax_rate", 0.22),
            retirement_contribution=config.get("retirement_contribution", 0),
            employer_match_rate=config.get("employer_match_rate", 0),
            use_roth=config.get("use_roth", False),
            retirement_withdrawal_tax_rate=config.get("retirement_withdrawal_tax_rate", 0.12),
        )
        balanced = run_simulation(
            377,
            1123,
            total_months=config.get("total_months", 480),
            annual_market_return=rate,
            capital_gains_tax_rate=config.get("capital_gains_tax_rate", 0.15),
            expense_ratio=config.get("expense_ratio", 0.001),
            inflation_rate=config.get("inflation_rate", 0.025),
            marginal_tax_rate=config.get("marginal_tax_rate", 0.22),
            retirement_contribution=config.get("retirement_contribution", 0),
            employer_match_rate=config.get("employer_match_rate", 0),
            use_roth=config.get("use_roth", False),
            retirement_withdrawal_tax_rate=config.get("retirement_withdrawal_tax_rate", 0.12),
        )

        diff_after_tax = (
            aggressive["final_net_worth_after_tax_real"]
            - balanced["final_net_worth_after_tax_real"]
        )
        winner_name = "Aggressive" if diff_after_tax > 0 else "Balanced"
        winner_style = "green" if diff_after_tax > 0 else "blue"

        results.append(
            {
                "rate": rate,
                "aggressive": aggressive["final_net_worth_after_tax_real"],
                "balanced": balanced["final_net_worth_after_tax_real"],
                "diff": diff_after_tax,
            }
        )

        table.add_row(
            f"{rate * 100:.0f}%",
            format_currency(aggressive['final_net_worth_after_tax_real']),
            format_currency(balanced['final_net_worth_after_tax_real']),
            f"[{winner_style}]{winner_name}[/{winner_style}]",
            f"[{winner_style}]{format_currency(abs(diff_after_tax))}[/{winner_style}]"
        )

    console.print(table)
    console.print()

    return results


def main():
    # Get loans for opening display
    loans = get_initial_loans()

    # Create loan details table
    loan_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    loan_table.add_column("Loan", style="cyan")
    loan_table.add_column("Balance", justify="right", style="yellow")
    loan_table.add_column("Rate", justify="right", style="magenta")
    loan_table.add_column("Min Payment", justify="right", style="green")

    total_balance = 0
    total_min_payment = 0

    for loan in loans:
        loan_table.add_row(
            loan.name,
            format_currency(loan.balance),
            f"{loan.annual_rate * 100:.2f}%",
            format_currency(loan.min_payment)
        )
        total_balance += loan.balance
        total_min_payment += loan.min_payment

    # Add total row
    loan_table.add_section()
    loan_table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{format_currency(total_balance)}[/bold]",
        "",
        f"[bold]{format_currency(total_min_payment)}[/bold]"
    )

    # Opening panel with text and table
    from rich.text import Text
    opening_text = Text()
    opening_text.append("🎓 Student Loan Payoff Analysis\n\n", style="bold")
    opening_text.append("Using your actual loan data\n", style="cyan")
    opening_text.append("Now with tax modeling, inflation, fees, AND retirement accounts!\n\n", style="dim")

    opening_content = Group(opening_text, loan_table)
    console.print(Panel(opening_content, title="[bold magenta]📋 Analysis Starting[/bold magenta]", border_style="magenta"))

    TIMELINE_YEARS = 40

    # Configuration
    config = {
        "total_months": TIMELINE_YEARS * 12,
        "annual_market_return": 0.07,
        "capital_gains_tax_rate": 0.15,  # 15% long-term capital gains
        "expense_ratio": 0.001,  # 0.1% for low-cost index fund
        "inflation_rate": 0.025,  # 2.5% inflation
        "marginal_tax_rate": 0.22,  # 22% tax bracket for deduction benefit (working years)
        "retirement_contribution": 0,  # No 401(k) in this model (already maxed separately)
        "employer_match_rate": 0.0,  # No match (already maxing employer match separately)
        "use_roth": False,  # Traditional 401(k) for pre-tax savings
        "retirement_withdrawal_tax_rate": 0.12,  # 12% tax bracket in retirement (typically lower)
    }

    aggressive = run_simulation(
        monthly_debt_allocation=1500,
        monthly_investment=0,
        **config,
    )

    balanced = run_simulation(
        monthly_debt_allocation=377,
        monthly_investment=1123,
        **config,
    )

    print_summary(aggressive, balanced, config)

    sensitivity_analysis(config=config)

    # Closing panel with key insights
    insights_text = "[bold green]✅ Analysis Complete![/bold green]\n\n"
    insights_text += "[cyan]Key Insights:[/cyan]\n\n"
    insights_text += "1. [yellow]Market return sensitivity[/yellow] - check sensitivity analysis for different scenarios\n"
    insights_text += "2. [yellow]Tax implications[/yellow]: 15% capital gains tax paid at liquidation\n"
    insights_text += "3. [yellow]Student loan interest deduction[/yellow] provides small tax benefit\n"
    insights_text += "4. [yellow]Time in market vs. debt-free psychology[/yellow] - choose what fits your goals"
    console.print(Panel(insights_text, title="[bold]💡 Key Takeaways[/bold]", border_style="green"))

    return aggressive, balanced


if __name__ == "__main__":
    aggressive, balanced = main()

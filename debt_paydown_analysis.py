"""
Student Loan Payoff vs. Investment Analysis
============================================
Compares two strategies over a 40-year horizon:
1. Aggressive: $1500/month all to debt (avalanche), then all to market
2. Balanced: $X/month to debt (avalanche), $1500 - X/month to market

Uses daily compound interest accrual and 7% annual stock market return.
Includes tax modeling, inflation adjustment, sensitivity analysis, and Monte Carlo simulation.
"""

import math
import random
from dataclasses import dataclass
from typing import Dict, List

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

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
    monthly_investment: float,
    annual_market_return: float = 0.07,
    expense_ratio: float = 0.001,
) -> tuple:
    """
    Simulate one month of debt payments and investment growth.

    Uses avalanche method: pay minimums first, then extra to highest rate.
    Applies expense ratio fees to investment returns.

    Returns: (extra_to_invest, new_investment_balance, interest_paid, investment_gains)
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

    # Step 5: Grow taxable investment balance (no tax on unrealized gains)
    monthly_expense_ratio = expense_ratio / 12
    gross_monthly_rate = (1 + annual_market_return) ** (1 / 12) - 1
    net_monthly_rate = (1 + gross_monthly_rate) * (1 - monthly_expense_ratio) - 1

    # Calculate investment gains
    investment_gains = investment_balance * net_monthly_rate

    # Update taxable investment balance (no capital gains tax until liquidation)
    investment_balance = investment_balance + investment_gains + total_to_invest

    return (
        extra_to_invest,
        investment_balance,
        total_interest_accrued,
        investment_gains,
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
    yearly_bonus_towards_debt: float = 0,
    yearly_bonus_towards_investments: float = 0,
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
        marginal_tax_rate: Tax rate for student loan interest deduction benefit
        yearly_bonus_towards_debt: One-time yearly payment towards debt (at end of year)
        yearly_bonus_towards_investments: One-time yearly payment towards investments (at end of year)

    Returns:
        Dictionary with monthly tracking data
    """
    loans = get_initial_loans()
    investment_balance = 0.0

    # Tracking
    history = {
        "month": [],
        "total_debt": [],
        "investment_balance": [],
        "net_worth": [],  # taxable investments - debt
        "debt_by_loan": {loan.name: [] for loan in loans},
        "cumulative_interest_paid": [],
        "cumulative_invested": [],
        "monthly_to_investments": [],
        "cumulative_investment_gains": [],
        "cumulative_loan_interest_deduction_value": [],
    }

    cumulative_interest = 0
    cumulative_invested = 0
    cumulative_investment_gains = 0
    cumulative_loan_interest_deduction = 0
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
            monthly_expense_ratio = expense_ratio / 12
            gross_monthly_rate = (1 + annual_market_return) ** (1 / 12) - 1
            net_monthly_rate = (1 + gross_monthly_rate) * (1 - monthly_expense_ratio) - 1

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
                interest,
                gains,
            ) = simulate_month(
                loans,
                monthly_debt_allocation,
                investment_balance,
                monthly_investment,
                annual_market_return,
                expense_ratio,
            )

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

        # Apply yearly bonus at end of year
        if month % 12 == 0 and (yearly_bonus_towards_debt > 0 or yearly_bonus_towards_investments > 0):
            # Check if all debt is paid off
            all_paid = all(l.is_paid_off() for l in loans)

            if all_paid:
                # All debt paid: entire bonus goes to investments
                monthly_expense_ratio = expense_ratio / 12
                gross_monthly_rate = (1 + annual_market_return) ** (1 / 12) - 1
                net_monthly_rate = (1 + gross_monthly_rate) * (1 - monthly_expense_ratio) - 1

                bonus_investment_gains = investment_balance * net_monthly_rate
                total_bonus = yearly_bonus_towards_debt + yearly_bonus_towards_investments
                investment_balance = investment_balance + bonus_investment_gains + total_bonus

                cumulative_invested += total_bonus
                cumulative_investment_gains += bonus_investment_gains
            else:
                # Still have debt: apply bonus to debt using avalanche method
                remaining_bonus = yearly_bonus_towards_debt

                # Pay minimums first with bonus (if any loans unpaid)
                for loan in loans:
                    if not loan.is_paid_off() and remaining_bonus > 0:
                        payment = loan.make_payment(min(loan.min_payment, remaining_bonus))
                        remaining_bonus -= payment

                # Apply extra bonus to highest interest rate loan (avalanche)
                active_loans = [l for l in loans if not l.is_paid_off()]
                active_loans.sort(key=lambda x: x.annual_rate, reverse=True)

                for loan in active_loans:
                    if remaining_bonus <= 0:
                        break
                    payment = loan.make_payment(remaining_bonus)
                    remaining_bonus -= payment

                # Any leftover bonus goes to investments along with investment bonus
                extra_to_invest = max(0, remaining_bonus)
                total_bonus_to_invest = yearly_bonus_towards_investments + extra_to_invest

                # Grow investment with bonus
                monthly_expense_ratio = expense_ratio / 12
                gross_monthly_rate = (1 + annual_market_return) ** (1 / 12) - 1
                net_monthly_rate = (1 + gross_monthly_rate) * (1 - monthly_expense_ratio) - 1

                bonus_investment_gains = investment_balance * net_monthly_rate
                investment_balance = investment_balance + bonus_investment_gains + total_bonus_to_invest

                cumulative_invested += total_bonus_to_invest
                cumulative_investment_gains += bonus_investment_gains

        # Record state after this month
        total_debt = sum(loan.balance for loan in loans)
        total_net_worth = investment_balance - total_debt
        history["month"].append(month)
        history["total_debt"].append(total_debt)
        history["investment_balance"].append(investment_balance)
        history["net_worth"].append(total_net_worth)
        history["cumulative_interest_paid"].append(cumulative_interest)
        history["cumulative_invested"].append(cumulative_invested)
        history["monthly_to_investments"].append(monthly_invested)
        history["cumulative_investment_gains"].append(cumulative_investment_gains)
        history["cumulative_loan_interest_deduction_value"].append(
            cumulative_loan_interest_deduction
        )

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

    history["debt_payoff_month"] = all_debt_paid_month
    history["final_investment"] = investment_balance
    history["final_investment_real"] = investment_balance / inflation_factor
    history["final_investment_after_tax"] = investment_after_tax
    history["final_investment_after_tax_real"] = investment_after_tax / inflation_factor
    history["final_net_worth"] = investment_balance
    history["final_net_worth_real"] = investment_balance / inflation_factor
    history["final_net_worth_after_tax"] = investment_after_tax
    history["final_net_worth_after_tax_real"] = investment_after_tax / inflation_factor
    history["total_interest_paid"] = cumulative_interest
    history["total_investment_gains"] = cumulative_investment_gains
    history["cost_basis"] = cost_basis
    history["capital_gains"] = capital_gains
    history["capital_gains_tax"] = capital_gains_tax
    history["total_loan_interest_deduction_value"] = cumulative_loan_interest_deduction
    history["inflation_factor"] = inflation_factor
    history["monthly_debt_allocation"] = monthly_debt_allocation
    history["yearly_bonus_towards_debt"] = yearly_bonus_towards_debt
    history["yearly_bonus_towards_investments"] = yearly_bonus_towards_investments

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


def print_summary(aggressive: Dict, balanced: Dict, config: Dict = None, budget: int = 1500, bonus_amount: int = 10000):
    """Print comparison summary of both strategies using Rich tables."""
    console.print()

    # Starting Conditions Panel
    loans = get_initial_loans()
    total_debt = sum(loan.balance for loan in loans)
    total_min = sum(loan.min_payment for loan in loans)

    conditions_text = f"[cyan]Total Debt:[/cyan] {format_currency(total_debt)}\n"
    conditions_text += f"[cyan]Total Minimum Payment:[/cyan] {format_currency(total_min)}/month\n"
    conditions_text += f"[cyan]Monthly Budget:[/cyan] {format_currency(budget)}\n"
    conditions_text += f"[cyan]Yearly Bonus:[/cyan] {format_currency(bonus_amount)}\n"

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
    agg_bonus_debt = aggressive.get('yearly_bonus_towards_debt', 0)
    agg_bonus_inv = aggressive.get('yearly_bonus_towards_investments', 0)
    bal_bonus_debt = balanced.get('yearly_bonus_towards_debt', 0)
    bal_bonus_inv = balanced.get('yearly_bonus_towards_investments', 0)

    # Build aggressive description
    agg_desc = f"${aggressive['monthly_debt_allocation']}/mo → debt then brokerage"
    if agg_bonus_debt > 0 or agg_bonus_inv > 0:
        if agg_bonus_debt > 0 and agg_bonus_inv == 0:
            agg_desc += f" + ${agg_bonus_debt:,.0f}/yr → debt"
        elif agg_bonus_debt == 0 and agg_bonus_inv > 0:
            agg_desc += f" + ${agg_bonus_inv:,.0f}/yr → investments"
        else:
            agg_desc += f" + ${agg_bonus_debt:,.0f}/yr → debt, ${agg_bonus_inv:,.0f}/yr → investments"

    # Build balanced description
    bal_desc = f"${balanced['monthly_debt_allocation']}/mo → debt, ${budget - balanced['monthly_debt_allocation']}/mo → brokerage"
    if bal_bonus_debt > 0 or bal_bonus_inv > 0:
        if bal_bonus_debt > 0 and bal_bonus_inv == 0:
            bal_desc += f" + ${bal_bonus_debt:,.0f}/yr → debt"
        elif bal_bonus_debt == 0 and bal_bonus_inv > 0:
            bal_desc += f" + ${bal_bonus_inv:,.0f}/yr → investments"
        else:
            bal_desc += f" + ${bal_bonus_debt:,.0f}/yr → debt, ${bal_bonus_inv:,.0f}/yr → investments"

    table.add_row(
        "[bold]Strategy Description[/bold]",
        agg_desc,
        bal_desc,
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

    pretax_diff_nominal = aggressive["final_net_worth"] - balanced["final_net_worth"]
    pretax_nominal_winner_style = "green" if pretax_diff_nominal > 0 else "blue"
    pretax_pct = abs(pretax_diff_nominal / balanced["final_net_worth"] * 100)

    table.add_row(
        "[bold]💰 Pre-Tax Final Net Worth (Nominal)[/bold]",
        f"[bold]{format_currency(aggressive['final_net_worth'])}[/bold]",
        f"[bold]{format_currency(balanced['final_net_worth'])}[/bold]",
        f"[{pretax_nominal_winner_style}][bold]{format_currency(abs(pretax_diff_nominal))} ({pretax_pct:.2f}%)[/bold][/{pretax_nominal_winner_style}]"
    )

    # Final results - Nominal dollars
    diff_nominal = aggressive["final_net_worth_after_tax"] - balanced["final_net_worth_after_tax"]
    nominal_winner_style = "green" if diff_nominal > 0 else "blue"
    nominal_pct = abs(diff_nominal / balanced["final_net_worth_after_tax"] * 100)

    table.add_row(
        "[bold]💰 After-Tax Final Net Worth (Nominal)[/bold]",
        f"[bold]{format_currency(aggressive['final_net_worth_after_tax'])}[/bold]",
        f"[bold]{format_currency(balanced['final_net_worth_after_tax'])}[/bold]",
        f"[{nominal_winner_style}][bold]{format_currency(abs(diff_nominal))} ({nominal_pct:.2f}%)[/bold][/{nominal_winner_style}]"
    )

    # Final results - Real dollars (inflation-adjusted)
    diff_after_tax = aggressive["final_net_worth_after_tax_real"] - balanced["final_net_worth_after_tax_real"]
    winner_style = "green" if diff_after_tax > 0 else "blue"
    winner_name = "Aggressive" if diff_after_tax > 0 else "Balanced"
    real_pct = abs(diff_after_tax / balanced["final_net_worth_after_tax_real"] * 100)

    table.add_row(
        "[bold]🏆 Final Net Worth (Real)[/bold]",
        f"[bold]{format_currency(aggressive['final_net_worth_after_tax_real'])}[/bold]",
        f"[bold]{format_currency(balanced['final_net_worth_after_tax_real'])}[/bold]",
        f"[{winner_style}][bold]{format_currency(abs(diff_after_tax))} ({real_pct:.2f}%)[/bold][/{winner_style}]"
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


def generate_monthly_returns(
    annual_mean_return: float,
    annual_volatility: float,
    num_months: int,
    seed: int = None,
) -> List[float]:
    """
    Generate random monthly returns using normal distribution.

    Args:
        annual_mean_return: Expected annual return (e.g., 0.07 for 7%)
        annual_volatility: Annual standard deviation (e.g., 0.18 for 18%)
        num_months: Number of months to generate
        seed: Random seed for reproducibility

    Returns:
        List of monthly returns
    """
    if seed is not None:
        random.seed(seed)

    # Convert annual metrics to monthly
    monthly_mean = (1 + annual_mean_return) ** (1 / 12) - 1
    monthly_std = annual_volatility / math.sqrt(12)

    # Generate random returns using Python's built-in normal distribution
    returns = []
    for _ in range(num_months):
        monthly_return = random.gauss(monthly_mean, monthly_std)
        returns.append(monthly_return)

    return returns


def run_simulation_with_variable_returns(
    monthly_debt_allocation: float,
    monthly_investment: float,
    monthly_returns: List[float],
    capital_gains_tax_rate: float = 0.15,
    expense_ratio: float = 0.001,
    inflation_rate: float = 0.025,
    marginal_tax_rate: float = 0.22,
    yearly_bonus_towards_debt: float = 0,
    yearly_bonus_towards_investments: float = 0,
) -> Dict:
    """
    Run simulation with variable monthly returns (for Monte Carlo).

    Similar to run_simulation but takes an array of monthly returns instead of fixed annual return.
    Uses capital gains tax at liquidation model (not monthly taxation).
    """
    loans = get_initial_loans()
    investment_balance = 0.0

    total_months = len(monthly_returns)
    cumulative_interest = 0
    cumulative_invested = 0
    all_debt_paid_month = None

    # Track student loan interest deduction per year
    current_year = -1
    year_interest_paid = 0
    year_deduction_used = 0

    for month in range(1, total_months + 1):
        # Check if all debt is paid off
        all_paid = all(loan.is_paid_off() for loan in loans)
        monthly_return = monthly_returns[month - 1]

        if all_paid:
            if all_debt_paid_month is None:
                all_debt_paid_month = month - 1

            # Calculate monthly rate after fees
            monthly_expense_ratio = expense_ratio / 12
            net_monthly_rate = (1 + monthly_return) * (1 - monthly_expense_ratio) - 1

            # Grow taxable account (no tax on unrealized gains)
            total_contribution = monthly_debt_allocation + monthly_investment
            investment_balance = (
                investment_balance * (1 + net_monthly_rate) + total_contribution
            )

            cumulative_invested += total_contribution
        else:
            # Accrue interest on loans (compound daily)
            total_interest_accrued = 0
            for loan in loans:
                if not loan.is_paid_off():
                    total_interest_accrued += loan.accrue_daily_interest(days=30)

            # Pay minimums
            remaining = monthly_debt_allocation
            for loan in loans:
                if not loan.is_paid_off():
                    payment = loan.make_payment(loan.min_payment)
                    remaining -= payment

            # Apply extra to highest rate loan (avalanche)
            active_loans = [l for l in loans if not l.is_paid_off()]
            active_loans.sort(key=lambda x: x.annual_rate, reverse=True)

            for loan in active_loans:
                if remaining <= 0:
                    break
                payment = loan.make_payment(remaining)
                remaining -= payment

            extra_to_invest = max(0, remaining)
            total_to_invest = monthly_investment + extra_to_invest

            # Calculate monthly rate after fees
            monthly_expense_ratio = expense_ratio / 12
            net_monthly_rate = (1 + monthly_return) * (1 - monthly_expense_ratio) - 1

            # Grow taxable account (no tax on unrealized gains)
            investment_balance = (
                investment_balance * (1 + net_monthly_rate) + total_to_invest
            )

            cumulative_invested += total_to_invest
            cumulative_interest += total_interest_accrued

            # Student loan interest deduction
            year = (month - 1) // 12
            if year != current_year:
                current_year = year
                year_interest_paid = 0
                year_deduction_used = 0

            year_interest_paid += total_interest_accrued

            annual_deduction_cap = 2500
            remaining_deduction = annual_deduction_cap - year_deduction_used

            if total_interest_accrued > 0 and remaining_deduction > 0:
                deductible_interest = min(total_interest_accrued, remaining_deduction)
                year_deduction_used += deductible_interest

        # Apply yearly bonus at end of year
        if month % 12 == 0 and (yearly_bonus_towards_debt > 0 or yearly_bonus_towards_investments > 0):
            # Check if all debt is paid off
            all_paid = all(l.is_paid_off() for l in loans)
            monthly_return = monthly_returns[month - 1]

            if all_paid:
                # All debt paid: entire bonus goes to investments
                monthly_expense_ratio = expense_ratio / 12
                net_monthly_rate = (1 + monthly_return) * (1 - monthly_expense_ratio) - 1

                total_bonus = yearly_bonus_towards_debt + yearly_bonus_towards_investments
                investment_balance = investment_balance * (1 + net_monthly_rate) + total_bonus

                cumulative_invested += total_bonus
            else:
                # Still have debt: apply bonus to debt using avalanche method
                remaining_bonus = yearly_bonus_towards_debt

                # Pay minimums first with bonus (if any loans unpaid)
                for loan in loans:
                    if not loan.is_paid_off() and remaining_bonus > 0:
                        payment = loan.make_payment(min(loan.min_payment, remaining_bonus))
                        remaining_bonus -= payment

                # Apply extra bonus to highest interest rate loan (avalanche)
                active_loans = [l for l in loans if not l.is_paid_off()]
                active_loans.sort(key=lambda x: x.annual_rate, reverse=True)

                for loan in active_loans:
                    if remaining_bonus <= 0:
                        break
                    payment = loan.make_payment(remaining_bonus)
                    remaining_bonus -= payment

                # Any leftover bonus goes to investments along with investment bonus
                extra_to_invest = max(0, remaining_bonus)
                total_bonus_to_invest = yearly_bonus_towards_investments + extra_to_invest

                # Grow investment with bonus
                monthly_expense_ratio = expense_ratio / 12
                net_monthly_rate = (1 + monthly_return) * (1 - monthly_expense_ratio) - 1

                investment_balance = investment_balance * (1 + net_monthly_rate) + total_bonus_to_invest

                cumulative_invested += total_bonus_to_invest

    # Calculate final values with capital gains tax at liquidation
    total_years = total_months // 12
    inflation_factor = (1 + inflation_rate) ** total_years

    # Calculate capital gains tax at liquidation (only on taxable account)
    cost_basis = cumulative_invested
    capital_gains = investment_balance - cost_basis
    capital_gains_tax = capital_gains * capital_gains_tax_rate
    investment_after_tax = investment_balance - capital_gains_tax

    return {
        "debt_payoff_month": all_debt_paid_month,
        "final_net_worth_after_tax_real": investment_after_tax / inflation_factor,
        "total_interest_paid": cumulative_interest,
    }


def sensitivity_analysis(
    market_returns: List[float] = None,
    config: Dict = None,
    yearly_bonus_towards_debt: float = 0,
    yearly_bonus_towards_investments: float = 0,
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
            yearly_bonus_towards_debt=yearly_bonus_towards_debt,
            yearly_bonus_towards_investments=yearly_bonus_towards_investments,
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
            yearly_bonus_towards_debt=yearly_bonus_towards_debt,
            yearly_bonus_towards_investments=yearly_bonus_towards_investments,
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


def monte_carlo_analysis(
    num_simulations: int = 1000,
    config: Dict = None,
    annual_volatility: float = 0.18,
    yearly_bonus_towards_debt: float = 0,
    yearly_bonus_towards_investments: float = 0,
):
    """
    Run Monte Carlo simulation with market volatility.

    Args:
        num_simulations: Number of simulations to run
        config: Configuration dict with parameters
        annual_volatility: Annual standard deviation (18% is typical for stocks)
        yearly_bonus_towards_debt: One-time yearly payment towards debt (at end of year)
        yearly_bonus_towards_investments: One-time yearly payment towards investments (at end of year)
    """
    if config is None:
        config = {}

    aggressive_results = []
    balanced_results = []
    aggressive_wins = 0

    for i in range(num_simulations):
        # Generate random monthly returns for this simulation
        monthly_returns = generate_monthly_returns(
            config.get("annual_market_return", 0.07),
            annual_volatility,
            config.get("total_months", 480),
            seed=i,  # Different seed for each simulation
        )

        # Run both strategies with same returns
        agg = run_simulation_with_variable_returns(
            1500,
            0,
            monthly_returns,
            config.get("capital_gains_tax_rate", 0.15),
            config.get("expense_ratio", 0.001),
            config.get("inflation_rate", 0.025),
            config.get("marginal_tax_rate", 0.22),
            yearly_bonus_towards_debt=yearly_bonus_towards_debt,
            yearly_bonus_towards_investments=yearly_bonus_towards_investments,
        )

        bal = run_simulation_with_variable_returns(
            377,
            1123,
            monthly_returns,
            config.get("capital_gains_tax_rate", 0.15),
            config.get("expense_ratio", 0.001),
            config.get("inflation_rate", 0.025),
            config.get("marginal_tax_rate", 0.22),
            yearly_bonus_towards_debt=yearly_bonus_towards_debt,
            yearly_bonus_towards_investments=yearly_bonus_towards_investments,
        )

        aggressive_results.append(agg["final_net_worth_after_tax_real"])
        balanced_results.append(bal["final_net_worth_after_tax_real"])

        if agg["final_net_worth_after_tax_real"] > bal["final_net_worth_after_tax_real"]:
            aggressive_wins += 1

    # Calculate statistics
    aggressive_results.sort()
    balanced_results.sort()

    def percentile(data, p):
        """Get percentile from sorted data."""
        k = (len(data) - 1) * p
        f = int(k)
        c = int(k) + 1 if k < len(data) - 1 else int(k)
        if f == c:
            return data[int(k)]
        return data[f] * (c - k) + data[c] * (k - f)

    # Create results table
    table = Table(
        title=f"🎲 Monte Carlo Results ({num_simulations:,} iterations) - After-Tax Real Dollars",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Percentile", style="cyan")
    table.add_column("Aggressive", justify="right", style="green")
    table.add_column("Balanced", justify="right", style="blue")
    table.add_column("Difference", justify="right")

    percentiles = [
        ("10th Percentile", 0.10),
        ("25th Percentile", 0.25),
        ("Median (50th)", 0.50),
        ("75th Percentile", 0.75),
        ("90th Percentile", 0.90),
    ]

    for label, p in percentiles:
        agg_val = percentile(aggressive_results, p)
        bal_val = percentile(balanced_results, p)
        diff = agg_val - bal_val
        diff_style = "green" if diff > 0 else "blue" if diff < 0 else "white"

        table.add_row(
            label,
            format_currency(agg_val),
            format_currency(bal_val),
            f"[{diff_style}]{format_currency(diff)}[/{diff_style}]",
        )

    console.print(table)

    # Probability panel
    prob_agg = aggressive_wins / num_simulations * 100
    prob_bal = (num_simulations - aggressive_wins) / num_simulations * 100
    winner_style = "green" if prob_agg > 50 else "blue"

    prob_text = f"[cyan]Annual Volatility:[/cyan] {annual_volatility * 100:.0f}%\n"
    prob_text += f"[cyan]Mean Return:[/cyan] {config.get('annual_market_return', 0.07) * 100:.1f}%\n\n"
    prob_text += f"[green]Probability Aggressive Wins:[/green] {prob_agg:.1f}%\n"
    prob_text += f"[blue]Probability Balanced Wins:[/blue] {prob_bal:.1f}%\n\n"
    prob_text += f"[{winner_style}]Most Likely Winner: {'Aggressive' if prob_agg > 50 else 'Balanced'}[/{winner_style}]"

    console.print(
        Panel(
            prob_text,
            title="[bold]📊 Probability Analysis[/bold]",
            border_style=winner_style,
        )
    )
    console.print()


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
    opening_text.append("Now with tax modeling, inflation, and fees!\n\n", style="dim")
    opening_content = Group(opening_text, loan_table)
    console.print(Panel(opening_content, title="[bold magenta]📋 Analysis Starting[/bold magenta]", border_style="magenta"))

    TIMELINE_YEARS = 40

    config = {
        "total_months": TIMELINE_YEARS * 12,
        "annual_market_return": 0.080, # USE CONSERVATIVE PRE-INFLATION-ADJUSTED AVERAGE RETURN
        "capital_gains_tax_rate": 0.15,  # 15% long-term capital gains
        "expense_ratio": 0.0010,  # 0.1% for low-cost index fund
        "inflation_rate": 0.025,  # 2.5% inflation
        "marginal_tax_rate": 0.22,  # 22% tax bracket for deduction benefit (working years)
    }

    aggressive = run_simulation(monthly_debt_allocation=1500, monthly_investment=0, yearly_bonus_towards_debt=10000, yearly_bonus_towards_investments=0, **config)
    balanced = run_simulation(monthly_debt_allocation=377, monthly_investment=1123, yearly_bonus_towards_debt=5000, yearly_bonus_towards_investments=5000, **config)

    print_summary(aggressive, balanced, config, budget=1500, bonus_amount=10000)

    # sensitivity_analysis(config=config)
    # monte_carlo_analysis(num_simulations=1000, config=config, annual_volatility=0.18)

    return aggressive, balanced


if __name__ == "__main__":
    aggressive, balanced = main()

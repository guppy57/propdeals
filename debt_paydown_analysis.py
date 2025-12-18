"""
Student Loan Payoff vs. Investment Analysis
============================================
Compares two strategies over a 40-year horizon:
1. Aggressive: $1500/month all to debt (avalanche), then all to market
2. Balanced: $400/month to debt (avalanche), $1100/month to market

Uses daily interest accrual and 7% annual stock market return.
"""

from dataclasses import dataclass
from typing import List, Dict


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
        """Accrue interest for given number of days. Returns interest added."""
        interest = self.balance * self.daily_rate * days
        self.balance += interest
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
) -> tuple:
    """
    Simulate one month of debt payments and investment growth.

    Uses avalanche method: pay minimums first, then extra to highest rate.

    Returns: (remaining_allocation_to_invest, new_investment_balance, interest_paid, principal_paid)
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

    principal_paid = 0
    for loan in active_loans:
        if remaining <= 0:
            break
        payment = loan.make_payment(remaining)
        principal_paid += payment
        remaining -= payment

    # Step 4: Any remaining allocation goes to investments
    extra_to_invest = max(0, remaining)
    total_to_invest = monthly_investment + extra_to_invest

    # Step 5: Grow investment balance (convert annual rate to equivalent monthly rate)
    # (1 + monthly_rate)^12 = (1 + annual_rate), so monthly_rate = (1 + annual_rate)^(1/12) - 1
    monthly_rate = (1 + annual_market_return) ** (1 / 12) - 1
    investment_balance = investment_balance * (1 + monthly_rate) + total_to_invest

    return extra_to_invest, investment_balance, total_interest_accrued, principal_paid


def run_simulation(
    monthly_debt_allocation: float,
    monthly_investment: float,
    total_months: int = 480,
    annual_market_return: float = 0.07,
) -> Dict:
    """
    Run full simulation for a given strategy.

    Args:
        monthly_debt_allocation: Fixed monthly amount for debt payments
        monthly_investment: Fixed monthly amount for investments
        total_months: Simulation duration (480 = 40 years)
        annual_market_return: Expected annual market return

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
        "net_worth": [],  # investments - debt
        "debt_by_loan": {loan.name: [] for loan in loans},
        "cumulative_interest_paid": [],
        "cumulative_invested": [],
        "monthly_to_investments": [],
    }

    cumulative_interest = 0
    cumulative_invested = 0
    all_debt_paid_month = None

    for month in range(1, total_months + 1):
        # Calculate current totals before this month's actions
        total_debt = sum(l.balance for l in loans)

        # Check if all debt is paid off
        all_paid = all(l.is_paid_off() for l in loans)

        if all_paid:
            if all_debt_paid_month is None:
                all_debt_paid_month = month - 1
            # All debt paid: full allocation goes to investments
            monthly_rate = (1 + annual_market_return) ** (1 / 12) - 1
            total_contribution = monthly_debt_allocation + monthly_investment
            investment_balance = (
                investment_balance * (1 + monthly_rate) + total_contribution
            )
            cumulative_invested += total_contribution
            monthly_invested = total_contribution
            interest_this_month = 0
        else:
            # Still have debt
            extra, investment_balance, interest, principal = simulate_month(
                loans,
                monthly_debt_allocation,
                investment_balance,
                monthly_investment,
                annual_market_return,
            )
            cumulative_interest += interest
            monthly_invested = monthly_investment + extra
            cumulative_invested += monthly_invested
            interest_this_month = interest

        # Record state after this month
        total_debt = sum(l.balance for l in loans)
        history["month"].append(month)
        history["total_debt"].append(total_debt)
        history["investment_balance"].append(investment_balance)
        history["net_worth"].append(investment_balance - total_debt)
        history["cumulative_interest_paid"].append(cumulative_interest)
        history["cumulative_invested"].append(cumulative_invested)
        history["monthly_to_investments"].append(monthly_invested)

        for loan in loans:
            history["debt_by_loan"][loan.name].append(loan.balance)

    history["debt_payoff_month"] = all_debt_paid_month
    history["final_investment"] = investment_balance
    history["final_net_worth"] = investment_balance
    history["total_interest_paid"] = cumulative_interest

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


def print_summary(aggressive: Dict, balanced: Dict):
    """Print comparison summary of both strategies."""
    print("\n" + "=" * 70)
    print("STUDENT LOAN PAYOFF STRATEGY COMPARISON")
    print("=" * 70)

    print("\n📊 STARTING CONDITIONS")
    print("-" * 40)
    loans = get_initial_loans()
    total_debt = sum(l.balance for l in loans)
    total_min = sum(l.min_payment for l in loans)
    print(f"  Total Debt:           {format_currency(total_debt)}")
    print(f"  Total Minimum Payment: {format_currency(total_min)}/month")
    print(f"  Monthly Budget:        {format_currency(1500)}")
    print(f"  Time Horizon:          40 years")
    print(f"  Assumed Market Return: 7% annually")

    print("\n" + "=" * 70)
    print("STRATEGY 1: AGGRESSIVE (Pay debt ASAP)")
    print("=" * 70)
    print(f"  Debt Allocation:    $1,500/month until paid off")
    print(f"  Investment:         $0/month until debt-free, then $1,500/month")
    print("-" * 40)
    print(
        f"  ⏱️  Debt Payoff Time:    {months_to_years_months(aggressive['debt_payoff_month'])}"
    )
    print(
        f"  💰 Total Interest Paid: {format_currency(aggressive['total_interest_paid'])}"
    )
    print(
        f"  📈 Final Investment:    {format_currency(aggressive['final_investment'])}"
    )
    print(f"  🏆 Final Net Worth:     {format_currency(aggressive['final_net_worth'])}")

    print("\n" + "=" * 70)
    print("STRATEGY 2: BALANCED (Invest while paying debt)")
    print("=" * 70)
    print(f"  Debt Allocation:    $400/month (avalanche method)")
    print(f"  Investment:         $1,100/month from start")
    print("-" * 40)
    print(
        f"  ⏱️  Debt Payoff Time:    {months_to_years_months(balanced['debt_payoff_month'])}"
    )
    print(
        f"  💰 Total Interest Paid: {format_currency(balanced['total_interest_paid'])}"
    )
    print(f"  📈 Final Investment:    {format_currency(balanced['final_investment'])}")
    print(f"  🏆 Final Net Worth:     {format_currency(balanced['final_net_worth'])}")

    print("\n" + "=" * 70)
    print("📊 COMPARISON")
    print("=" * 70)

    diff = aggressive["final_net_worth"] - balanced["final_net_worth"]
    winner = "AGGRESSIVE" if diff > 0 else "BALANCED"

    print(f"  Net Worth Difference:     {format_currency(abs(diff))}")
    print(f"  Winner:                   {winner} strategy")

    interest_diff = balanced["total_interest_paid"] - aggressive["total_interest_paid"]
    print(f"  Extra Interest (Balanced): {format_currency(interest_diff)}")

    payoff_diff = balanced["debt_payoff_month"] - aggressive["debt_payoff_month"]
    print(f"  Extra Time in Debt:        {months_to_years_months(payoff_diff)}")

    # Calculate when balanced catches up (if ever)
    for i, month in enumerate(aggressive["month"]):
        if balanced["net_worth"][i] > aggressive["net_worth"][i]:
            crossover_month = month
            print(
                f"\n  📍 Balanced overtakes Aggressive at: Month {crossover_month} ({months_to_years_months(crossover_month)})"
            )
            break
    else:
        print(f"\n  📍 Aggressive stays ahead for entire 40-year period")

    print("\n" + "=" * 70)

def sensitivity_analysis(
    market_returns: List[float] = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10],
):
    """Run sensitivity analysis on different market return assumptions."""
    print("\n" + "=" * 70)
    print("SENSITIVITY ANALYSIS: Market Return Impact")
    print("=" * 70)
    print(
        f"{'Return':<10} {'Aggressive':<18} {'Balanced':<18} {'Winner':<12} {'Difference':<15}"
    )
    print("-" * 70)

    results = []
    for rate in market_returns:
        aggressive = run_simulation(1500, 0, annual_market_return=rate)
        balanced = run_simulation(400, 1100, annual_market_return=rate)

        diff = aggressive["final_net_worth"] - balanced["final_net_worth"]
        winner = "Aggressive" if diff > 0 else "Balanced"

        results.append(
            {
                "rate": rate,
                "aggressive": aggressive["final_net_worth"],
                "balanced": balanced["final_net_worth"],
                "diff": diff,
            }
        )

        print(
            f"{rate * 100:.0f}%{'':<7} {format_currency(aggressive['final_net_worth']):<18} "
            f"{format_currency(balanced['final_net_worth']):<18} {winner:<12} {format_currency(abs(diff)):<15}"
        )

    return results


def main():
    print("\n🎓 Running Student Loan Payoff Analysis...")
    print("   Using your actual loan data from the screenshot")

    TIMELINE_YEARS = 40

    aggressive = run_simulation(
        monthly_debt_allocation=1500,
        monthly_investment=0,
        total_months=TIMELINE_YEARS * 12,
        annual_market_return=0.07,
    )

    balanced = run_simulation(
        monthly_debt_allocation=377,
        monthly_investment=1100,
        total_months=TIMELINE_YEARS * 12,
        annual_market_return=0.07,
    )

    print_summary(aggressive, balanced)

    sensitivity_analysis()

    print("\n✅ Analysis complete!")

    return aggressive, balanced


if __name__ == "__main__":
    aggressive, balanced = main()

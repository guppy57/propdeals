"""
Student Loan Payoff vs. Investment Analysis
============================================
Compares two strategies over a 40-year horizon:
1. Aggressive: $1500/month all to debt (avalanche), then all to market
2. Balanced: $400/month to debt (avalanche), $1100/month to market

Uses daily interest accrual and 7% annual stock market return.
Includes tax modeling, inflation adjustment, and Monte Carlo simulation.
"""

from dataclasses import dataclass
from typing import List, Dict
import random


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
              interest_paid, principal_paid, investment_gains, retirement_gains)
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
    net_monthly_rate = gross_monthly_rate - monthly_expense_ratio

    # Retirement account grows without capital gains tax (either tax-deferred or Roth)
    retirement_gains = retirement_balance * net_monthly_rate
    retirement_balance = retirement_balance + retirement_gains + total_retirement_deposit

    # Step 7: Grow taxable investment balance with fees and taxes
    # Calculate investment gains before tax
    gross_gains = investment_balance * net_monthly_rate

    # Apply capital gains tax on taxable account
    taxes_on_gains = gross_gains * capital_gains_tax_rate
    after_tax_gains = gross_gains - taxes_on_gains

    # Update taxable investment balance
    investment_balance = investment_balance + after_tax_gains + total_to_invest

    return (
        extra_to_invest,
        investment_balance,
        retirement_balance,
        total_interest_accrued,
        principal_paid,
        after_tax_gains,
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
        retirement_contribution: Monthly contribution to 401(k)/IRA
        employer_match_rate: Employer match as % of contribution (e.g., 0.5 = 50%)
        use_roth: True for Roth IRA (after-tax), False for traditional 401(k) (pre-tax)

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
        "cumulative_tax_on_gains": [],
        "cumulative_loan_interest_deduction_value": [],
        "cumulative_pretax_savings": [],
    }

    cumulative_interest = 0
    cumulative_invested = 0
    cumulative_retirement_contributed = 0
    cumulative_employer_match = 0
    cumulative_investment_gains = 0
    cumulative_retirement_gains = 0
    cumulative_tax_on_gains = 0
    cumulative_loan_interest_deduction = 0
    cumulative_pretax_savings = 0
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
            # Apply fees and taxes even after debt is paid off
            monthly_expense_ratio = expense_ratio / 12
            gross_monthly_rate = (1 + annual_market_return) ** (1 / 12) - 1
            net_monthly_rate = gross_monthly_rate - monthly_expense_ratio

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

            # Calculate gains and taxes on taxable account
            gross_gains = investment_balance * net_monthly_rate
            taxes_on_gains = gross_gains * capital_gains_tax_rate
            after_tax_gains = gross_gains - taxes_on_gains

            total_contribution = monthly_debt_allocation + monthly_investment
            investment_balance = investment_balance + after_tax_gains + total_contribution

            cumulative_invested += total_contribution
            cumulative_investment_gains += after_tax_gains
            cumulative_tax_on_gains += taxes_on_gains
            monthly_invested = total_contribution
            interest_this_month = 0
        else:
            # Still have debt
            (
                extra,
                investment_balance,
                retirement_balance,
                interest,
                principal,
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
            # Calculate tax paid on gains
            if gains > 0:
                gross_gains = gains / (1 - capital_gains_tax_rate)
                taxes_on_gains = gross_gains - gains
                cumulative_tax_on_gains += taxes_on_gains
            interest_this_month = interest

        # Calculate student loan interest deduction value (capped at $2,500/year)
        # Track annual interest for deduction purposes
        year = (month - 1) // 12
        year_start_month = year * 12 + 1

        # Sum interest paid this calendar year so far
        year_interest_so_far = sum(
            cumulative_interest if i == month else 0
            for i in range(year_start_month, month + 1)
        )

        # For simplicity, calculate deduction on a monthly basis with annual cap
        annual_deduction_cap = 2500
        monthly_deduction_cap = annual_deduction_cap / 12

        # Deductible interest this month (simplified - assumes even distribution)
        if interest_this_month > 0:
            deductible_interest = min(interest_this_month, monthly_deduction_cap)
            tax_benefit = deductible_interest * marginal_tax_rate
            cumulative_loan_interest_deduction += tax_benefit

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
        history["cumulative_tax_on_gains"].append(cumulative_tax_on_gains)
        history["cumulative_loan_interest_deduction_value"].append(
            cumulative_loan_interest_deduction
        )
        history["cumulative_pretax_savings"].append(cumulative_pretax_savings)

        for loan in loans:
            history["debt_by_loan"][loan.name].append(loan.balance)

    # Apply inflation adjustment to final values
    total_years = total_months / 12
    inflation_factor = (1 + inflation_rate) ** total_years

    # Calculate total account values
    total_account_value = investment_balance + retirement_balance

    # For traditional 401k, account for withdrawal taxes
    retirement_after_tax = retirement_balance
    if not use_roth:
        # Traditional 401k: pay taxes on withdrawal
        retirement_after_tax = retirement_balance * (1 - marginal_tax_rate)

    total_account_value_after_tax = investment_balance + retirement_after_tax

    history["debt_payoff_month"] = all_debt_paid_month
    history["final_investment"] = investment_balance
    history["final_investment_real"] = investment_balance / inflation_factor
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
    history["total_tax_on_gains"] = cumulative_tax_on_gains
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
    """Print comparison summary of both strategies."""
    print("\n" + "=" * 70)
    print("STUDENT LOAN PAYOFF STRATEGY COMPARISON")
    print("=" * 70)

    print("\n📊 STARTING CONDITIONS")
    print("-" * 40)
    loans = get_initial_loans()
    total_debt = sum(loan.balance for loan in loans)
    total_min = sum(loan.min_payment for loan in loans)
    print(f"  Total Debt:              {format_currency(total_debt)}")
    print(f"  Total Minimum Payment:   {format_currency(total_min)}/month")
    print(f"  Monthly Budget:          {format_currency(1500)}")

    if config:
        years = config.get("total_months", 480) // 12
        print(f"  Time Horizon:            {years} years")
        print(f"  Market Return:           {config.get('annual_market_return', 0.07) * 100:.1f}% annually")
        print(f"  Capital Gains Tax:       {config.get('capital_gains_tax_rate', 0.15) * 100:.0f}%")
        print(f"  Expense Ratio:           {config.get('expense_ratio', 0.001) * 100:.2f}%")
        print(f"  Inflation Rate:          {config.get('inflation_rate', 0.025) * 100:.1f}%")
        print(f"  Marginal Tax Rate:       {config.get('marginal_tax_rate', 0.22) * 100:.0f}%")

    print("\n" + "=" * 70)
    print("STRATEGY 1: AGGRESSIVE (Pay debt ASAP)")
    print("=" * 70)
    print("  Debt Allocation:    $1,500/month until paid off")
    print("  Taxable Investment: $0/month until debt-free, then $1,500/month")
    if config and config.get("retirement_contribution", 0) > 0:
        print(
            f"  Retirement:         {format_currency(config.get('retirement_contribution', 0))}/month to "
            + ("Roth IRA" if config.get("use_roth") else "401(k)")
        )
        if config.get("employer_match_rate", 0) > 0:
            print(
                f"                      + {config.get('employer_match_rate', 0) * 100:.0f}% employer match"
            )
    print("-" * 40)
    print(
        f"  ⏱️  Debt Payoff Time:    {months_to_years_months(aggressive['debt_payoff_month'])}"
    )
    print(
        f"  💰 Total Interest Paid: {format_currency(aggressive['total_interest_paid'])}"
    )
    print(
        f"  💸 Loan Interest Tax Benefit: {format_currency(aggressive['total_loan_interest_deduction_value'])}"
    )
    print(
        f"  📈 Taxable Investment (Nominal):  {format_currency(aggressive['final_investment'])}"
    )
    print(
        f"  📈 Taxable Investment (Real):     {format_currency(aggressive['final_investment_real'])}"
    )
    if aggressive.get("final_retirement", 0) > 0:
        print(
            f"  🏦 Retirement Account (Nominal):  {format_currency(aggressive['final_retirement'])}"
        )
        print(
            f"  🏦 Retirement Account (Real):     {format_currency(aggressive['final_retirement_real'])}"
        )
        print(
            f"  🏦 Retirement After-Tax (Real):   {format_currency(aggressive['final_retirement_after_tax_real'])}"
        )
        print(
            f"  💼 Total Employer Match:          {format_currency(aggressive['total_employer_match'])}"
        )
        if not aggressive["use_roth"]:
            print(
                f"  💰 Total Pre-Tax Savings:         {format_currency(aggressive['total_pretax_savings'])}"
            )
    print(
        f"  📊 Total Investment Gains:        {format_currency(aggressive['total_investment_gains'])}"
    )
    print(
        f"  💵 Total Tax on Gains:            {format_currency(aggressive['total_tax_on_gains'])}"
    )
    print(
        f"  🏆 Final Net Worth (Nominal):     {format_currency(aggressive['final_net_worth'])}"
    )
    print(
        f"  🏆 Final Net Worth (Real):        {format_currency(aggressive['final_net_worth_real'])}"
    )
    print(
        f"  🏆 Final After-Tax (Real):        {format_currency(aggressive['final_net_worth_after_tax_real'])}"
    )

    print("\n" + "=" * 70)
    print("STRATEGY 2: BALANCED (Invest while paying debt)")
    print("=" * 70)
    print("  Debt Allocation:    $377/month (avalanche method)")
    print("  Taxable Investment: $1,123/month from start")
    if config and config.get("retirement_contribution", 0) > 0:
        print(
            f"  Retirement:         {format_currency(config.get('retirement_contribution', 0))}/month to "
            + ("Roth IRA" if config.get("use_roth") else "401(k)")
        )
        if config.get("employer_match_rate", 0) > 0:
            print(
                f"                      + {config.get('employer_match_rate', 0) * 100:.0f}% employer match"
            )
    print("-" * 40)
    print(
        f"  ⏱️  Debt Payoff Time:    {months_to_years_months(balanced['debt_payoff_month'])}"
    )
    print(
        f"  💰 Total Interest Paid: {format_currency(balanced['total_interest_paid'])}"
    )
    print(
        f"  💸 Loan Interest Tax Benefit: {format_currency(balanced['total_loan_interest_deduction_value'])}"
    )
    print(
        f"  📈 Taxable Investment (Nominal):  {format_currency(balanced['final_investment'])}"
    )
    print(
        f"  📈 Taxable Investment (Real):     {format_currency(balanced['final_investment_real'])}"
    )
    if balanced.get("final_retirement", 0) > 0:
        print(
            f"  🏦 Retirement Account (Nominal):  {format_currency(balanced['final_retirement'])}"
        )
        print(
            f"  🏦 Retirement Account (Real):     {format_currency(balanced['final_retirement_real'])}"
        )
        print(
            f"  🏦 Retirement After-Tax (Real):   {format_currency(balanced['final_retirement_after_tax_real'])}"
        )
        print(
            f"  💼 Total Employer Match:          {format_currency(balanced['total_employer_match'])}"
        )
        if not balanced["use_roth"]:
            print(
                f"  💰 Total Pre-Tax Savings:         {format_currency(balanced['total_pretax_savings'])}"
            )
    print(
        f"  📊 Total Investment Gains:        {format_currency(balanced['total_investment_gains'])}"
    )
    print(
        f"  💵 Total Tax on Gains:            {format_currency(balanced['total_tax_on_gains'])}"
    )
    print(
        f"  🏆 Final Net Worth (Nominal):     {format_currency(balanced['final_net_worth'])}"
    )
    print(
        f"  🏆 Final Net Worth (Real):        {format_currency(balanced['final_net_worth_real'])}"
    )
    print(
        f"  🏆 Final After-Tax (Real):        {format_currency(balanced['final_net_worth_after_tax_real'])}"
    )

    print("\n" + "=" * 70)
    print("📊 COMPARISON")
    print("=" * 70)

    diff_nominal = aggressive["final_net_worth"] - balanced["final_net_worth"]
    diff_real = aggressive["final_net_worth_real"] - balanced["final_net_worth_real"]
    diff_after_tax = (
        aggressive["final_net_worth_after_tax_real"]
        - balanced["final_net_worth_after_tax_real"]
    )
    winner = "AGGRESSIVE" if diff_after_tax > 0 else "BALANCED"

    print(f"  Net Worth Difference (Nominal): {format_currency(abs(diff_nominal))}")
    print(f"  Net Worth Difference (Real):    {format_currency(abs(diff_real))}")
    print(
        f"  Net Worth Difference (After-Tax Real): {format_currency(abs(diff_after_tax))}"
    )
    print(f"  Winner (based on after-tax):    {winner} strategy")

    interest_diff = balanced["total_interest_paid"] - aggressive["total_interest_paid"]
    print(f"  Extra Interest (Balanced):      {format_currency(interest_diff)}")

    tax_benefit_diff = (
        balanced["total_loan_interest_deduction_value"]
        - aggressive["total_loan_interest_deduction_value"]
    )
    print(f"  Extra Tax Benefit (Balanced):   {format_currency(tax_benefit_diff)}")

    tax_on_gains_diff = balanced["total_tax_on_gains"] - aggressive["total_tax_on_gains"]
    print(f"  Extra Tax on Gains (Balanced):  {format_currency(tax_on_gains_diff)}")

    if config and config.get("employer_match_rate", 0) > 0:
        match_diff = (
            balanced["total_employer_match"] - aggressive["total_employer_match"]
        )
        print(f"  Extra Employer Match (Balanced): {format_currency(match_diff)}")

    payoff_diff = balanced["debt_payoff_month"] - aggressive["debt_payoff_month"]
    print(f"  Extra Time in Debt:             {months_to_years_months(payoff_diff)}")

    # Calculate when balanced catches up (if ever)
    for i, month in enumerate(aggressive["month"]):
        if balanced["net_worth"][i] > aggressive["net_worth"][i]:
            crossover_month = month
            print(
                f"\n  📍 Balanced overtakes Aggressive at: Month {crossover_month} ({months_to_years_months(crossover_month)})"
            )
            break
    else:
        print("\n  📍 Aggressive stays ahead for entire period")

    print("\n" + "=" * 70)

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
    monthly_std = annual_volatility / (12 ** 0.5)

    # Generate random returns using Box-Muller transform
    returns = []
    for _ in range(num_months):
        # Box-Muller transform to get normal distribution
        u1 = random.random()
        u2 = random.random()
        z = (-2 * (u1 if u1 > 0 else 1e-10) ** 0.5) * (2 * 3.14159 * u2) ** 0.5
        # Simplified: just use a basic normal approximation
        # More accurate would be: z = sqrt(-2 * ln(u1)) * cos(2 * pi * u2)
        # For simplicity, use central limit theorem approximation
        z = sum(random.random() for _ in range(12)) - 6  # Approximate N(0,1)
        monthly_return = monthly_mean + monthly_std * z
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
    retirement_contribution: float = 0.0,
    employer_match_rate: float = 0.0,
    use_roth: bool = False,
) -> Dict:
    """
    Run simulation with variable monthly returns (for Monte Carlo).

    Similar to run_simulation but takes an array of monthly returns instead of fixed annual return.
    """
    loans = get_initial_loans()
    investment_balance = 0.0
    retirement_balance = 0.0

    total_months = len(monthly_returns)
    cumulative_interest = 0
    cumulative_invested = 0
    cumulative_retirement_contributed = 0
    cumulative_employer_match = 0
    cumulative_investment_gains = 0
    cumulative_retirement_gains = 0
    cumulative_tax_on_gains = 0
    cumulative_loan_interest_deduction = 0
    cumulative_pretax_savings = 0
    all_debt_paid_month = None

    for month in range(1, total_months + 1):
        # Check if all debt is paid off
        all_paid = all(loan.is_paid_off() for loan in loans)
        monthly_return = monthly_returns[month - 1]

        if all_paid:
            if all_debt_paid_month is None:
                all_debt_paid_month = month - 1

            # Grow retirement account
            monthly_expense_ratio = expense_ratio / 12
            net_monthly_rate = monthly_return - monthly_expense_ratio

            ret_gains = retirement_balance * net_monthly_rate
            employer_match = retirement_contribution * employer_match_rate
            retirement_balance = (
                retirement_balance + ret_gains + retirement_contribution + employer_match
            )

            cumulative_retirement_contributed += retirement_contribution
            cumulative_employer_match += employer_match
            cumulative_retirement_gains += ret_gains

            if not use_roth:
                cumulative_pretax_savings += retirement_contribution * marginal_tax_rate

            # Grow taxable account
            gross_gains = investment_balance * net_monthly_rate
            taxes_on_gains = gross_gains * capital_gains_tax_rate
            after_tax_gains = gross_gains - taxes_on_gains

            total_contribution = monthly_debt_allocation + monthly_investment
            investment_balance = (
                investment_balance + after_tax_gains + total_contribution
            )

            cumulative_invested += total_contribution
            cumulative_investment_gains += after_tax_gains
            cumulative_tax_on_gains += taxes_on_gains
        else:
            # Accrue interest on loans
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

            # Grow retirement account
            monthly_expense_ratio = expense_ratio / 12
            net_monthly_rate = monthly_return - monthly_expense_ratio

            ret_gains = retirement_balance * net_monthly_rate
            employer_match = retirement_contribution * employer_match_rate
            retirement_balance = (
                retirement_balance + ret_gains + retirement_contribution + employer_match
            )

            cumulative_retirement_contributed += retirement_contribution
            cumulative_employer_match += employer_match
            cumulative_retirement_gains += ret_gains

            if not use_roth:
                cumulative_pretax_savings += retirement_contribution * marginal_tax_rate

            # Grow taxable account
            gross_gains = investment_balance * net_monthly_rate
            taxes_on_gains = gross_gains * capital_gains_tax_rate
            after_tax_gains = gross_gains - taxes_on_gains

            investment_balance = investment_balance + after_tax_gains + total_to_invest

            cumulative_invested += total_to_invest
            cumulative_investment_gains += after_tax_gains
            cumulative_tax_on_gains += taxes_on_gains
            cumulative_interest += total_interest_accrued

            # Student loan interest deduction
            if total_interest_accrued > 0:
                monthly_deduction_cap = 2500 / 12
                deductible_interest = min(total_interest_accrued, monthly_deduction_cap)
                tax_benefit = deductible_interest * marginal_tax_rate
                cumulative_loan_interest_deduction += tax_benefit

    # Calculate final values
    total_years = total_months / 12
    inflation_factor = (1 + inflation_rate) ** total_years

    total_account_value = investment_balance + retirement_balance
    retirement_after_tax = retirement_balance
    if not use_roth:
        retirement_after_tax = retirement_balance * (1 - marginal_tax_rate)
    total_account_value_after_tax = investment_balance + retirement_after_tax

    return {
        "debt_payoff_month": all_debt_paid_month,
        "final_net_worth_after_tax_real": total_account_value_after_tax
        / inflation_factor,
        "final_net_worth_real": total_account_value / inflation_factor,
        "total_interest_paid": cumulative_interest,
    }


def monte_carlo_analysis(
    num_simulations: int = 1000,
    config: Dict = None,
    annual_volatility: float = 0.18,
):
    """
    Run Monte Carlo simulation with market volatility.

    Args:
        num_simulations: Number of simulations to run
        config: Configuration dict with parameters
        annual_volatility: Annual standard deviation (18% is typical for stocks)
    """
    if config is None:
        config = {}

    print("\n" + "=" * 70)
    print(f"MONTE CARLO SIMULATION ({num_simulations:,} iterations)")
    print("=" * 70)
    print(f"Annual Volatility: {annual_volatility * 100:.0f}%")
    print(f"Mean Return: {config.get('annual_market_return', 0.07) * 100:.1f}%")
    print()

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
            config.get("retirement_contribution", 0),
            config.get("employer_match_rate", 0),
            config.get("use_roth", False),
        )

        bal = run_simulation_with_variable_returns(
            377,
            1123,
            monthly_returns,
            config.get("capital_gains_tax_rate", 0.15),
            config.get("expense_ratio", 0.001),
            config.get("inflation_rate", 0.025),
            config.get("marginal_tax_rate", 0.22),
            config.get("retirement_contribution", 0),
            config.get("employer_match_rate", 0),
            config.get("use_roth", False),
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

    print("Results (After-Tax Real Dollars):")
    print("-" * 70)
    print(
        f"{'Metric':<25} {'Aggressive':<20} {'Balanced':<20} {'Difference':<15}"
    )
    print("-" * 70)
    print(
        f"{'10th Percentile':<25} {format_currency(percentile(aggressive_results, 0.10)):<20} "
        f"{format_currency(percentile(balanced_results, 0.10)):<20} "
        f"{format_currency(percentile(aggressive_results, 0.10) - percentile(balanced_results, 0.10)):<15}"
    )
    print(
        f"{'25th Percentile':<25} {format_currency(percentile(aggressive_results, 0.25)):<20} "
        f"{format_currency(percentile(balanced_results, 0.25)):<20} "
        f"{format_currency(percentile(aggressive_results, 0.25) - percentile(balanced_results, 0.25)):<15}"
    )
    print(
        f"{'Median (50th)':<25} {format_currency(percentile(aggressive_results, 0.50)):<20} "
        f"{format_currency(percentile(balanced_results, 0.50)):<20} "
        f"{format_currency(percentile(aggressive_results, 0.50) - percentile(balanced_results, 0.50)):<15}"
    )
    print(
        f"{'75th Percentile':<25} {format_currency(percentile(aggressive_results, 0.75)):<20} "
        f"{format_currency(percentile(balanced_results, 0.75)):<20} "
        f"{format_currency(percentile(aggressive_results, 0.75) - percentile(balanced_results, 0.75)):<15}"
    )
    print(
        f"{'90th Percentile':<25} {format_currency(percentile(aggressive_results, 0.90)):<20} "
        f"{format_currency(percentile(balanced_results, 0.90)):<20} "
        f"{format_currency(percentile(aggressive_results, 0.90) - percentile(balanced_results, 0.90)):<15}"
    )
    print()
    print(
        f"Probability Aggressive Wins: {aggressive_wins / num_simulations * 100:.1f}%"
    )
    print(f"Probability Balanced Wins:   {(num_simulations - aggressive_wins) / num_simulations * 100:.1f}%")
    print("=" * 70)


def sensitivity_analysis(
    market_returns: List[float] = None,
    config: Dict = None,
):
    """Run sensitivity analysis on different market return assumptions."""
    if market_returns is None:
        market_returns = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10]

    if config is None:
        config = {}

    print("\n" + "=" * 70)
    print("SENSITIVITY ANALYSIS: Market Return Impact")
    print("=" * 70)
    print(
        f"{'Return':<10} {'Aggressive (Real)':<22} {'Balanced (Real)':<22} {'Winner':<12} {'Difference':<15}"
    )
    print("-" * 70)

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
        )

        diff_after_tax = (
            aggressive["final_net_worth_after_tax_real"]
            - balanced["final_net_worth_after_tax_real"]
        )
        winner = "Aggressive" if diff_after_tax > 0 else "Balanced"

        results.append(
            {
                "rate": rate,
                "aggressive": aggressive["final_net_worth_after_tax_real"],
                "balanced": balanced["final_net_worth_after_tax_real"],
                "diff": diff_after_tax,
            }
        )

        print(
            f"{rate * 100:.0f}%{'':<7} {format_currency(aggressive['final_net_worth_after_tax_real']):<22} "
            f"{format_currency(balanced['final_net_worth_after_tax_real']):<22} {winner:<12} {format_currency(abs(diff_after_tax)):<15}"
        )

    return results


def main():
    print("\n🎓 Running Student Loan Payoff Analysis...")
    print("   Using your actual loan data")
    print("   Now with tax modeling, inflation, fees, AND retirement accounts!")

    TIMELINE_YEARS = 40

    # Configuration
    config = {
        "total_months": TIMELINE_YEARS * 12,
        "annual_market_return": 0.07,
        "capital_gains_tax_rate": 0.15,  # 15% long-term capital gains
        "expense_ratio": 0.001,  # 0.1% for low-cost index fund
        "inflation_rate": 0.025,  # 2.5% inflation
        "marginal_tax_rate": 0.22,  # 22% tax bracket for deduction benefit
        "retirement_contribution": 0,  # No 401(k) in this model (already maxed separately)
        "employer_match_rate": 0.0,  # No match (already maxing employer match separately)
        "use_roth": False,  # Traditional 401(k) for pre-tax savings
    }

    aggressive = run_simulation(
        monthly_debt_allocation=1500,  # $1,500 to debt until paid off, then to brokerage
        monthly_investment=0,
        **config,
    )

    balanced = run_simulation(
        monthly_debt_allocation=377,  # $377 to debt, $1,123 to brokerage
        monthly_investment=1123,
        **config,
    )

    print_summary(aggressive, balanced, config)

    sensitivity_analysis(config=config)

    # Run Monte Carlo simulation
    monte_carlo_analysis(num_simulations=1000, config=config, annual_volatility=0.18)

    print("\n✅ Analysis complete!")
    print("\nKey Insights:")
    print("  1. Market volatility matters - check Monte Carlo results for risk")
    print("  2. Tax implications: 15% capital gains tax reduces investment returns")
    print("  3. Student loan interest deduction provides small tax benefit")
    print("  4. Time in market vs. debt-free psychology - choose what fits your goals")

    return aggressive, balanced


if __name__ == "__main__":
    aggressive, balanced = main()

from datetime import datetime
from fpdf import FPDF
from helpers import format_currency, format_percentage, format_number, express_percent_as_months_and_days


class PropertyPDF(FPDF):
    """Custom PDF class for property analysis reports"""

    def __init__(self, property_address):
        super().__init__()
        self.property_address = property_address

    def header(self):
        self.set_font('Helvetica', 'B', 16)
        self.cell(0, 10, 'Property Investment Analysis', align='C', new_x='LMARGIN', new_y='NEXT')
        self.set_font('Helvetica', '', 10)
        self.cell(0, 6, self.property_address, align='C', new_x='LMARGIN', new_y='NEXT')
        self.cell(0, 6, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}', align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')

    def section_title(self, title):
        self.set_font('Helvetica', 'B', 12)
        self.set_fill_color(230, 230, 230)
        self.cell(0, 8, title, fill=True, new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def info_line(self, label, value):
        self.set_font('Helvetica', '', 10)
        self.cell(60, 6, label + ':', new_x='RIGHT')
        self.set_font('Helvetica', 'B', 10)
        self.cell(0, 6, str(value), new_x='LMARGIN', new_y='NEXT')


def export_property_analysis(row, rents_df, after_tax_monthly_income, loan_info=None, assumptions=None, output_path=None):
    """
    Export property analysis to PDF.

    Args:
        row: pandas Series containing property data (single row from df)
        rents_df: DataFrame containing rent data for the property's units
        after_tax_monthly_income: float, user's monthly after-tax income
        loan_info: dict, optional loan parameters (interest_rate, down_payment_rate, years, etc.)
        assumptions: dict, optional investment assumptions (appreciation_rate, vacancy_rate, etc.)
        output_path: str, optional path for output PDF. If None, auto-generates from address

    Returns:
        str: Path to the generated PDF file
    """
    property_address = row['address1']

    # Generate output path if not provided
    if output_path is None:
        safe_address = property_address.replace(' ', '_').replace(',', '').replace('.', '')
        output_path = f"{safe_address}_analysis.pdf"

    # Create PDF
    pdf = PropertyPDF(property_address)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # 1. Property Overview
    pdf.section_title('Property Overview')
    pdf.info_line('Address', property_address)
    pdf.info_line('Purchase Price', format_currency(row['purchase_price']))
    pdf.info_line('Bedrooms', int(row['beds']))
    pdf.info_line('Bathrooms', int(row['baths']))
    pdf.info_line('Square Feet', f"{int(row['square_ft']):,}")
    pdf.info_line('Year Built', f"{int(row['built_in'])} (Age: {int(row['home_age'])} years)")
    pdf.info_line('Units', int(row['units']))
    pdf.info_line('Cost per Sq Ft', format_currency(row['cost_per_sqrft']))
    pdf.ln(5)

    # 2. Loan Details & Assumptions
    if loan_info or assumptions:
        pdf.section_title('Loan Details & Assumptions')

        if loan_info:
            pdf.set_font('Helvetica', 'B', 10)
            pdf.cell(0, 6, 'Loan Details:', new_x='LMARGIN', new_y='NEXT')
            pdf.set_font('Helvetica', '', 10)
            if 'name' in loan_info:
                pdf.info_line('Loan Type', loan_info['name'])
            if 'interest_rate' in loan_info:
                pdf.info_line('Interest Rate', format_percentage(loan_info['interest_rate']))
            if 'apr_rate' in loan_info:
                pdf.info_line('APR', format_percentage(loan_info['apr_rate']))
            if 'down_payment_rate' in loan_info:
                pdf.info_line('Down Payment', format_percentage(loan_info['down_payment_rate']))
            if 'years' in loan_info:
                pdf.info_line('Loan Term', f"{loan_info['years']} years")
            if 'mip_upfront_rate' in loan_info:
                pdf.info_line('MIP Upfront', format_percentage(loan_info['mip_upfront_rate']))
            if 'mip_annual_rate' in loan_info:
                pdf.info_line('MIP Annual', format_percentage(loan_info['mip_annual_rate']))
            pdf.ln(3)

        if assumptions:
            pdf.set_font('Helvetica', 'B', 10)
            pdf.cell(0, 6, 'Investment Assumptions:', new_x='LMARGIN', new_y='NEXT')
            pdf.set_font('Helvetica', '', 10)
            if 'appreciation_rate' in assumptions:
                pdf.info_line('Appreciation Rate', format_percentage(assumptions['appreciation_rate']))
            if 'rent_appreciation_rate' in assumptions:
                pdf.info_line('Rent Appreciation', format_percentage(assumptions['rent_appreciation_rate']))
            if 'property_tax_rate' in assumptions:
                pdf.info_line('Property Tax Rate', format_percentage(assumptions['property_tax_rate']))
            if 'home_insurance_rate' in assumptions:
                pdf.info_line('Home Insurance Rate', format_percentage(assumptions['home_insurance_rate']))
            if 'vacancy_rate' in assumptions:
                pdf.info_line('Vacancy Rate', format_percentage(assumptions['vacancy_rate']))
            if 'repair_savings_rate' in assumptions:
                pdf.info_line('Repair Reserve', format_percentage(assumptions['repair_savings_rate']))
            if 'capex_reserve_rate' in assumptions:
                pdf.info_line('CapEx Reserve', format_percentage(assumptions['capex_reserve_rate']))
            if 'closing_costs_rate' in assumptions:
                pdf.info_line('Closing Costs Rate', format_percentage(assumptions['closing_costs_rate']))
            if 'discount_rate' in assumptions:
                pdf.info_line('Discount Rate', format_percentage(assumptions['discount_rate']))
            # Fixed constants
            pdf.info_line('Federal Tax Rate', '22.00%')
            pdf.info_line('Depreciation Period', '27.5 years')
        pdf.ln(5)

    # 3. Unit Rent Estimates
    pdf.section_title('Unit Rent Estimates')

    property_rents = rents_df[rents_df['address1'] == property_address]
    your_unit_index = property_rents['rent_estimate'].idxmin()

    # Table header
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(200, 200, 200)
    col_widths = [20, 50, 40, 40]
    headers = ['Unit', 'Configuration', 'Monthly Rent', 'Status']
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 7, header, border=1, fill=True, align='C')
    pdf.ln()

    # Table rows
    pdf.set_font('Helvetica', '', 9)
    total_monthly_rent = 0
    for idx, rent_row in property_rents.iterrows():
        is_your_unit = idx == your_unit_index
        unit_config = f"{int(rent_row['beds'])}-bed {int(rent_row['baths'])}-bath"
        status = "Your Unit" if is_your_unit else "Rental"

        pdf.cell(col_widths[0], 6, str(int(rent_row['unit_num'])), border=1, align='C')
        pdf.cell(col_widths[1], 6, unit_config, border=1)
        pdf.cell(col_widths[2], 6, format_currency(rent_row['rent_estimate']), border=1, align='R')
        pdf.cell(col_widths[3], 6, status, border=1, align='C')
        pdf.ln()
        total_monthly_rent += rent_row['rent_estimate']

    # Total row
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(col_widths[0] + col_widths[1], 6, 'Total', border=1)
    pdf.cell(col_widths[2], 6, format_currency(total_monthly_rent), border=1, align='R')
    pdf.cell(col_widths[3], 6, '', border=1)
    pdf.ln(8)

    # 4. Income Breakdown
    pdf.section_title('Income Breakdown')
    pdf.info_line('Total Monthly Rent (All Units)', format_currency(row['total_rent']))
    pdf.info_line('Your Unit Rent (Not Collected)', format_currency(row['min_rent']))
    pdf.info_line('Net Monthly Income (Year 1)', format_currency(row['net_rent_y1']))
    pdf.info_line('Full Rental Income (Year 2)', format_currency(row['total_rent']))
    pdf.ln(3)

    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 6, 'Operating Expenses:', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 10)
    monthly_opex = row['operating_expenses']
    pdf.info_line('Monthly Operating Expenses', f"{format_currency(monthly_opex)} ({format_currency(monthly_opex * 12)} annually)")
    pdf.ln(3)

    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 6, 'Net Operating Income (NOI):', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 10)
    pdf.info_line('NOI Year 1 (Live-in)', f"{format_currency(row['net_rent_y1'] - monthly_opex)} ({format_currency(row['annual_NOI_y1'])} annually)")
    pdf.info_line('NOI Year 2 (All Rent)', f"{format_currency(row['monthly_NOI'])} ({format_currency(row['annual_NOI_y2'])} annually)")
    pdf.ln(3)

    pdf.info_line('After-Tax Monthly Income', format_currency(after_tax_monthly_income))
    pdf.info_line('Housing Cost to Income Ratio', format_percentage(row['costs_to_income']))
    pdf.ln(5)

    # 5. Investment Metrics (Year 1 vs Year 2)
    pdf.section_title('Investment Metrics')

    # Table header
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(200, 200, 200)
    metric_col_widths = [70, 50, 50]
    metric_headers = ['Metric', 'Year 1 (Live-in)', 'Year 2 (All Rent)']
    for i, header in enumerate(metric_headers):
        pdf.cell(metric_col_widths[i], 7, header, border=1, fill=True, align='C')
    pdf.ln()

    # Metrics data
    metrics = [
        ('Monthly Cash Flow', format_currency(row['monthly_cash_flow_y1']), format_currency(row['monthly_cash_flow_y2'])),
        ('Annual Cash Flow', format_currency(row['annual_cash_flow_y1']), format_currency(row['annual_cash_flow_y2'])),
        ('After-Tax Cash Flow', format_currency(row['after_tax_cash_flow_y1']), format_currency(row['after_tax_cash_flow_y2'])),
        ('Cap Rate', format_percentage(row['cap_rate_y1']), format_percentage(row['cap_rate_y2'])),
        ('Cash on Cash Return', format_percentage(row['CoC_y1']), format_percentage(row['CoC_y2'])),
        ('Gross Rent Multiplier', format_number(row['GRM_y1']), format_number(row['GRM_y2'])),
        ('Annual Rent', format_currency(row['annual_rent_y1']), format_currency(row['annual_rent_y2'])),
        ('1% Rule (MGR/PP)', '', format_percentage(row['MGR_PP'])),
        ('50% Rule (OpEx/Rent)', '', format_percentage(row['OpEx_Rent'])),
        ('DSCR (Rent/Mortgage)', '', format_number(row['DSCR'])),
        ('LTV Ratio', '', format_percentage(row['ltv_ratio'])),
        ('Price Per Door', '', format_currency(row['price_per_door'])),
        ('Rent Per Sqft', '', format_currency(row['rent_per_sqft'])),
        ('Break-Even Occupancy', '', format_percentage(row['break_even_occupancy'])),
        ('Break-Even Vacancy', '', express_percent_as_months_and_days(row['break_even_vacancy'])),
        ('Operating Expense Ratio', '', format_percentage(row['oer'])),
        ('Effective Gross Income', '', format_currency(row['egi'])),
        ('Debt Yield', '', format_percentage(row['debt_yield'])),
        ('Monthly Depreciation', '', format_currency(row['monthly_depreciation'])),
        ('Monthly Tax Savings', '', format_currency(row['tax_savings_monthly'])),
        ('Return on Equity (ROE) Y2', '', format_percentage(row['roe_y2'])),
        ('Leverage Benefit', '', format_percentage(row['leverage_benefit'])),
        ('Payback Period', '', f"{row['payback_period_years']:.1f} years" if row['payback_period_years'] != float('inf') else "Never"),
        ('Cash Flow (10% Rent Drop)', format_currency(row['cash_flow_y1_downside_10pct']), format_currency(row['cash_flow_y2_downside_10pct'])),
    ]

    pdf.set_font('Helvetica', '', 9)
    for metric in metrics:
        pdf.cell(metric_col_widths[0], 6, metric[0], border=1)
        pdf.cell(metric_col_widths[1], 6, metric[1], border=1, align='R')
        pdf.cell(metric_col_widths[2], 6, metric[2], border=1, align='R')
        pdf.ln()
    pdf.ln(5)

    # 6. Investment Projections
    pdf.section_title('Investment Projections')

    # Table header
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(200, 200, 200)
    proj_col_widths = [55, 40, 40, 40]
    proj_headers = ['Metric', '5Y', '10Y', '20Y']
    for i, header in enumerate(proj_headers):
        pdf.cell(proj_col_widths[i], 7, header, border=1, fill=True, align='C')
    pdf.ln()

    # Projections data
    projections = [
        ('Investment Gain', format_currency(row['5y_forecast']), format_currency(row['10y_forecast']), format_currency(row['20y_forecast'])),
        ('Future Value', format_currency(row['future_value_5yr']), format_currency(row['future_value_10yr']), format_currency(row['future_value_20yr'])),
        ('Net Proceeds', format_currency(row['net_proceeds_5yr']), format_currency(row['net_proceeds_10yr']), format_currency(row['net_proceeds_20yr'])),
        ('Equity Multiple', format_number(row['equity_multiple_5yr']), format_number(row['equity_multiple_10yr']), format_number(row['equity_multiple_20yr'])),
        ('Avg Annual Return %', format_percentage(row['avg_annual_return_5yr'] / 100), format_percentage(row['avg_annual_return_10yr'] / 100), format_percentage(row['avg_annual_return_20yr'] / 100)),
        ('IRR', format_percentage(row['irr_5yr']), format_percentage(row['irr_10yr']), format_percentage(row['irr_20yr'])),
        ('NPV', format_currency(row['npv_5yr']), format_currency(row['npv_10yr']), format_currency(row['npv_20yr'])),
        ('Fair Value', '---', format_currency(row['fair_value_10yr']), '---'),
        ('Value Gap %', '---', format_percentage(row['value_gap_pct_10yr'] / 100), '---'),
    ]

    pdf.set_font('Helvetica', '', 9)
    for proj in projections:
        pdf.cell(proj_col_widths[0], 6, proj[0], border=1)
        pdf.cell(proj_col_widths[1], 6, proj[1], border=1, align='R')
        pdf.cell(proj_col_widths[2], 6, proj[2], border=1, align='R')
        pdf.cell(proj_col_widths[3], 6, proj[3], border=1, align='R')
        pdf.ln()
    pdf.ln(5)

    # 7. Deal Score Breakdown
    pdf.section_title('Investment Criteria Breakdown')

    # Calculate scores (same logic as analyze_property)
    # Y2 cashflow scoring - property-type specific
    if row["units"] == 0:  # Single family
        cf_y2_score = (3 if row["monthly_cash_flow_y2"] > 300 else
                       2 if row["monthly_cash_flow_y2"] >= -50 else 0)
    else:  # Multi-family
        cf_y2_score = (3 if row["monthly_cash_flow_y2"] > 500 else
                       2 if row["monthly_cash_flow_y2"] > 400 else
                       1 if row["monthly_cash_flow_y2"] > 200 else 0)
    cf_y1_bonus = (3 if row["monthly_cash_flow_y1"] > 0 else 2 if row["monthly_cash_flow_y1"] > -400 else 0)
    coc_score = (3 if row["CoC_y2"] > 0.15 else 2 if row["CoC_y2"] > 0.12 else 1 if row["CoC_y2"] > 0.08 else 0)
    cap_score = (1 if row["cap_rate_y2"] > 0.06 else 0)
    mgr_score = (2 if row["MGR_PP"] >= 0.01 else 1 if row["MGR_PP"] >= 0.008 else 0)
    opex_score = (2 if 0.4 <= row["OpEx_Rent"] <= 0.6 else 1 if 0.3 <= row["OpEx_Rent"] <= 0.7 else 0)
    dscr_score = (2 if row["DSCR"] >= 1.25 else 1 if row["DSCR"] >= 1.1 else 0)
    cash_score = (2 if row["cash_needed"] < 20000 else 1 if row["cash_needed"] < 30000 else 0)
    grm_score = (1 if row["GRM_y2"] < 12 else 0)
    sqft_score = (2 if row["cost_per_sqrft"] < 100 else 1 if row["cost_per_sqrft"] < 150 else 0)
    age_score = (2 if row["home_age"] < 20 else 0)
    irr_score = (2 if row["irr_10yr"] >= 0.15 else 1 if row["irr_10yr"] >= 0.12 else 0)
    at_cf_score = (2 if row["after_tax_cash_flow_y2"] > 600 else 1 if row["after_tax_cash_flow_y2"] > 400 else 0)
    payback_score = (2 if row["payback_period_years"] < 7 and row["payback_period_years"] != float('inf') else
                     1 if row["payback_period_years"] < 10 and row["payback_period_years"] != float('inf') else 0)
    downside_y1_score = (2 if row["cash_flow_y1_downside_10pct"] > 0 else 1 if row["cash_flow_y1_downside_10pct"] > -200 else 0)
    downside_y2_score = (1 if row["cash_flow_y2_downside_10pct"] > 0 else 0)
    equity_mult_score = (2 if row["equity_multiple_10yr"] >= 3 else 1 if row["equity_multiple_10yr"] >= 2 else 0)
    roe_score = (2 if row["roe_y2"] >= 0.20 else 1 if row["roe_y2"] >= 0.15 else 0)
    leverage_score = (2 if row["leverage_benefit"] >= 0.05 else 1 if row["leverage_benefit"] >= 0.02 else 0)
    breakeven_score = (1 if row["break_even_occupancy"] < 0.80 else 0)
    proceeds_score = (1 if row["net_proceeds_10yr"] > 100000 else 0)
    npv_score = (1 if row["npv_10yr"] > 20000 else 0)

    # Table header
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_fill_color(200, 200, 200)
    criteria_col_widths = [55, 15, 15, 85]
    criteria_headers = ['Criteria', 'Score', 'Max', 'Details']
    for i, header in enumerate(criteria_headers):
        pdf.cell(criteria_col_widths[i], 7, header, border=1, fill=True, align='C')
    pdf.ln()

    payback_display = f"{row['payback_period_years']:.1f} yrs" if row['payback_period_years'] != float('inf') else "Never"

    criteria = [
        ('Cash Flow Y2', cf_y2_score, 3, f"${row['monthly_cash_flow_y2']:.0f}/month"),
        ('Cash Flow Y1 Bonus', cf_y1_bonus, 3, f"${row['monthly_cash_flow_y1']:.0f}/month"),
        ('Cash-on-Cash Return', coc_score, 3, f"{row['CoC_y2']:.1%}"),
        ('Cap Rate', cap_score, 1, f"{row['cap_rate_y2']:.1%}"),
        ('1% Rule', mgr_score, 2, f"{row['MGR_PP']:.2%}"),
        ('50% Rule', opex_score, 2, f"{row['OpEx_Rent']:.1%}"),
        ('DSCR', dscr_score, 2, f"{row['DSCR']:.2f}"),
        ('Cash Needed', cash_score, 2, f"${row['cash_needed']:,.0f}"),
        ('GRM', grm_score, 1, f"{row['GRM_y2']:.1f}"),
        ('Cost per Sqft', sqft_score, 2, f"${row['cost_per_sqrft']:.0f}"),
        ('Property Age', age_score, 2, f"{row['home_age']:.0f} years"),
        ('IRR (10yr)', irr_score, 2, f"{row['irr_10yr']:.1%}"),
        ('After-Tax CF Y2', at_cf_score, 2, f"${row['after_tax_cash_flow_y2']:.0f}/month"),
        ('Payback Period', payback_score, 2, payback_display),
        ('Y1 Rent Drop (10%)', downside_y1_score, 2, f"${row['cash_flow_y1_downside_10pct']:.0f}/month"),
        ('Y2 Rent Drop (10%)', downside_y2_score, 1, f"${row['cash_flow_y2_downside_10pct']:.0f}/month"),
        ('Equity Multiple (10yr)', equity_mult_score, 2, f"{row['equity_multiple_10yr']:.2f}x"),
        ('ROE Y2', roe_score, 2, f"{row['roe_y2']:.1%}"),
        ('Leverage Benefit', leverage_score, 2, f"{row['leverage_benefit']:.1%}"),
        ('Break-Even Occupancy', breakeven_score, 1, f"{row['break_even_occupancy']:.1%}"),
        ('Net Proceeds (10yr)', proceeds_score, 1, f"${row['net_proceeds_10yr']:,.0f}"),
        ('NPV (10yr)', npv_score, 1, f"${row['npv_10yr']:,.0f}"),
    ]

    pdf.set_font('Helvetica', '', 8)
    for crit in criteria:
        pdf.cell(criteria_col_widths[0], 5, crit[0], border=1)
        pdf.cell(criteria_col_widths[1], 5, str(crit[1]), border=1, align='C')
        pdf.cell(criteria_col_widths[2], 5, str(crit[2]), border=1, align='C')
        pdf.cell(criteria_col_widths[3], 5, crit[3], border=1)
        pdf.ln()

    # 8. Mobility Scores
    pdf.section_title('Mobility Score Breakdown')

    # Table header
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(200, 200, 200)
    mobility_col_widths = [50, 30, 30, 30, 30]
    mobility_headers = ['Metric', 'Score', 'Max', 'Weight', 'Result']
    for i, header in enumerate(mobility_headers):
        pdf.cell(mobility_col_widths[i], 7, header, border=1, fill=True, align='C')
    pdf.ln()

    walk_score = row['walk_score']
    transit_score = row['transit_score']
    bike_score = row['bike_score']
    total_mobility_score = row['mobility_score']

    walk_weight = 0.6
    transit_weight = 0.3
    bike_weight = 0.1

    mobility_data = [
        ('Walk Score', walk_score, 100, walk_weight, walk_score * walk_weight),
        ('Transit Score', transit_score, 100, transit_weight, transit_score * transit_weight),
        ('Bike Score', bike_score, 100, bike_weight, bike_score * bike_weight),
    ]

    pdf.set_font('Helvetica', '', 9)
    for mob in mobility_data:
        pdf.cell(mobility_col_widths[0], 6, mob[0], border=1)
        pdf.cell(mobility_col_widths[1], 6, f"{mob[1]:.0f}", border=1, align='C')
        pdf.cell(mobility_col_widths[2], 6, str(mob[2]), border=1, align='C')
        pdf.cell(mobility_col_widths[3], 6, f"{mob[3]:.0%}", border=1, align='C')
        pdf.cell(mobility_col_widths[4], 6, f"{mob[4]:.2f}", border=1, align='C')
        pdf.ln()

    # Total row
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(mobility_col_widths[0], 6, 'TOTAL SCORE', border=1)
    pdf.cell(mobility_col_widths[1], 6, f"{total_mobility_score:.2f}", border=1, align='C')
    pdf.cell(mobility_col_widths[2], 6, '100', border=1, align='C')
    pdf.cell(mobility_col_widths[3], 6, '', border=1)
    pdf.cell(mobility_col_widths[4], 6, f"{total_mobility_score:.2f}", border=1, align='C')
    pdf.ln(8)

    # 9. Cost Breakdown
    pdf.section_title('Cost Breakdown')

    # Table header
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(200, 200, 200)
    cost_col_widths = [60, 55, 55]
    cost_headers = ['Cost Type', 'Monthly Amount', 'Annual Amount']
    for i, header in enumerate(cost_headers):
        pdf.cell(cost_col_widths[i], 7, header, border=1, fill=True, align='C')
    pdf.ln()

    costs = [
        ('Mortgage Payment', row['monthly_mortgage']),
        ('MIP (Insurance)', row['monthly_mip']),
        ('Property Taxes', row['monthly_taxes']),
        ('Home Insurance', row['monthly_insurance']),
        ('Vacancy Reserve', row['monthly_vacancy_costs']),
        ('Repair Reserve', row['monthly_repair_costs']),
    ]

    pdf.set_font('Helvetica', '', 9)
    for cost in costs:
        pdf.cell(cost_col_widths[0], 6, cost[0], border=1)
        pdf.cell(cost_col_widths[1], 6, format_currency(cost[1]), border=1, align='R')
        pdf.cell(cost_col_widths[2], 6, format_currency(cost[1] * 12), border=1, align='R')
        pdf.ln()

    # Total cost row
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(cost_col_widths[0], 6, 'Total Monthly Cost', border=1)
    pdf.cell(cost_col_widths[1], 6, format_currency(row['total_monthly_cost']), border=1, align='R')
    pdf.cell(cost_col_widths[2], 6, format_currency(row['total_monthly_cost'] * 12), border=1, align='R')
    pdf.ln()

    # Electricity estimate
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(cost_col_widths[0], 6, 'Electricity (est.)', border=1)
    pdf.cell(cost_col_widths[1], 6, format_currency(row['annual_electricity_cost_est'] / 12), border=1, align='R')
    pdf.cell(cost_col_widths[2], 6, format_currency(row['annual_electricity_cost_est']), border=1, align='R')
    pdf.ln(8)

    # 10. Investment Summary
    pdf.section_title('Investment Summary')
    pdf.info_line('Down Payment', format_currency(row['down_payment']))
    pdf.info_line('Closing Costs', format_currency(row['closing_costs']))
    pdf.info_line('Total Cash Needed', format_currency(row['cash_needed']))
    pdf.info_line('Loan Amount', format_currency(row['loan_amount']))

    # Save PDF
    pdf.output(output_path)

    return output_path

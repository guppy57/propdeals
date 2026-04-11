import os

import pandas as pd
import questionary
from dotenv import load_dotenv
from InquirerPy import inquirer
from rich.console import Console
from rich.panel import Panel
from supabase import Client, create_client

from add_property import run_add_property
from assumptions import AssumptionsProvider
from display import (
    display_all_phase1_qualifying_properties,
    display_all_properties,
    display_all_properties_info,
    display_current_context_panel,
    display_investment_requirements_panel,
    display_loans,
    display_new_property_qualification,
    display_phase1_research_list,
    display_phase1_total_rent_differences,
    display_property_investment_metrics_table,
    display_property_metrics,
    display_property_overview_panel,
    display_property_rent_estimates_table,
    display_start_screen_summary,
    display_y2_calculations, display_closing_costs_table,
)
from exporter import export_property_analysis
from handlers import (
    handle_changing_loan,
    handle_extract_neighborhood_grade,
    handle_generate_rent_estimates,
    handle_neighborhood_analysis,
    handle_price_change,
    handle_property_summary,
    handle_property_wide_research_generation,
    handle_rent_research_after_add,
    handle_rent_research_generation,
    handle_risk_assessment,
    handle_scrape_neighborhood_from_findneighborhoods,
    handle_status_change,
    handle_view_research_reports, handle_delete_property,
)
from helpers import (
    calculate_additional_room_rent,
    calculate_monthly_take_home,
    get_properties_missing_tours,
    is_property_assessment_done_vectorized,
)
from dataframe_helpers import (
    apply_calculations_on_dataframe,
    apply_investment_calculations
)
from inspections import InspectionsClient
from loans import LoansProvider
from neighborhood_assessment import edit_neighborhood_assessment
from neighborhood_scraper import NeighborhoodScraper
from neighborhoods import NeighborhoodsClient
from property_assessment import edit_property_assessment
from scripts import ScriptsProvider

load_dotenv()

console = Console()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
inspections = InspectionsClient(supabase_client=supabase)
neighborhoods = NeighborhoodsClient(supabase_client=supabase, console=console)
scraper = NeighborhoodScraper(supabase_client=supabase, console=console)
assumptions_provider = AssumptionsProvider(supabase_client=supabase, console=console)
loan_provider = LoansProvider(supabase_client=supabase, console=console)

LAST_USED_LOAN = 12
CASH_NEEDED_AMT = 40000

PHASE0_CRITERIA = f"square_ft >= 1900 & cash_needed <= {CASH_NEEDED_AMT} & monthly_cash_flow >= -600 & (baths/beds) >= 0.4 & purchase_price >= 100000"
PHASE1_CRITERIA = (
    "MGR_PP > 0.01 & OpEx_Rent < 0.5 & DSCR > 1.25 & beats_market "
    "& mr_monthly_cash_flow_y1 >= -700 "
    "& ((units == 0 & mr_monthly_cash_flow_y2 >= -100) | (units > 0 & mr_monthly_cash_flow_y2 >= 200))"
)
# PHASE1_TOUR_CRITERIA = "status == 'active' & neighborhood_letter_grade in ['A', 'B', 'C']"
PHASE1_TOUR_CRITERIA = "status == 'active'"

def load_assumptions():
    global ASSUMPTIONS
    console.print("[yellow]Reloading assumptions...[/yellow]")
    assumption = assumptions_provider.get_assumption_by_id(1)
    if not assumption:
        console.print("[red]Failed to load assumptions![/red]")
        return

    # Convert Assumption dataclass to dictionary for backward compatibility
    ASSUMPTIONS = {
        "appreciation_rate": float(assumption.appreciation_rate),
        "mf_appreciation_rate": (float(assumption.appreciation_rate) - 0.01),
        "rent_appreciation_rate": float(assumption.rent_appreciation_rate),
        "property_tax_rate": float(assumption.property_tax_rate),
        "home_insurance_rate": float(assumption.home_insurance_rate),
        "vacancy_rate": float(assumption.vacancy_rate),
        "repair_savings_rate": float(assumption.repair_savings_rate),
        "capex_reserve_rate": float(assumption.capex_reserve_rate),
        "closing_costs_rate": float(assumption.closing_costs_rate),
        "live_in_unit_setting": assumption.live_in_unit_setting,
        "gross_annual_income": assumption.gross_annual_income,
        "state_tax_code": assumption.state_tax_code,
        "after_tax_monthly_income": calculate_monthly_take_home(assumption.gross_annual_income, assumption.state_tax_code),
        "discount_rate": assumption.discount_rate,
        "utility_electric_base": float(assumption.utility_electric_base),
        "utility_gas_base": float(assumption.utility_gas_base),
        "utility_water_base": float(assumption.utility_water_base),
        "utility_trash_base": float(assumption.utility_trash_base),
        "utility_internet_base": float(assumption.utility_internet_base),
        "utility_baseline_sqft": int(assumption.utility_baseline_sqft),
        "land_value_prcnt": float(assumption.land_value_prcnt),
        "federal_tax_rate": float(assumption.federal_tax_rate),
        "selling_costs_rate": float(assumption.selling_costs_rate),
        "longterm_capital_gains_tax_rate": float(assumption.longterm_capital_gains_tax_rate),
        "residential_depreciation_period_yrs": float(assumption.residential_depreciation_period_yrs),
        "default_property_condition_score": int(assumption.default_property_condition_score),
        "description": assumption.description,
    }
    console.print(
        f"[green]Assumption set '{assumption.description}' reloaded successfully![/green]"
    )


def load_loan(loan_id):
    global LOAN
    console.print("[yellow]Reloading loan data...[/yellow]")
    loan = loan_provider.get_loan_by_id(loan_id)
    LOAN = {
        "name": loan.name,
        "interest_rate": loan.interest_rate,
        "apr_rate": loan.apr_rate,
        "down_payment_rate": loan.down_payment_rate,
        "loan_length_years": loan.years,
        "mip_upfront_rate": loan.mip_upfront_rate,
        "mip_annual_rate": loan.mip_annual_rate,
        "upfront_discounts": loan.upfront_discounts,
        "loan_type": loan.loan_type,
        "using_ifa_loan": loan.using_ifa_loan,
        "lender_fees": loan.lender_fees,
        "pmi_amount": loan.pmi_amount
    }
    console.print(f"[green]Loan {loan.name} data reloaded successfully![/green]")



def reload_dataframe():
    global df, rents
    console.print("[yellow]Reloading property data...[/yellow]")
    properties_get_response = (
        supabase.table("properties").select("*").limit(10000).execute()
    )
    df = pd.DataFrame(properties_get_response.data)
    rents_get_response = (
        supabase.table("rent_estimates").select("*").limit(10000).execute()
    )
    rents = pd.DataFrame(rents_get_response.data)
    rents = rents.drop(["id"], axis=1)
    rent_summary = (
        rents.groupby("address1")["rent_estimate"].agg(["sum", "min"]).reset_index()
    )
    rent_summary.columns = ["address1", "market_total_rent_estimate", "min_rent"]
    min_rent_indices = rents.groupby("address1")["rent_estimate"].idxmin()
    min_rent_units = rents.loc[
        min_rent_indices, ["address1", "unit_num", "beds"]
    ].reset_index(drop=True)
    min_rent_units.columns = ["address1", "min_rent_unit", "min_rent_unit_beds"]
    rent_summary = rent_summary.merge(min_rent_units, on="address1", how="left")
    df = df.merge(rent_summary, on="address1", how="left")

    # Get owner's unit sqft from rent_estimates (min_rent_unit is the unit owner lives in)
    owner_unit_sqft = rents.loc[
        rents.groupby("address1")["rent_estimate"].idxmin(),
        ["address1", "estimated_sqrft"],
    ].rename(columns={"estimated_sqrft": "owner_unit_sqft"})

    # Merge owner unit sqft into main dataframe
    df = df.merge(owner_unit_sqft, on="address1", how="left")

    # Fill missing owner_unit_sqft: use total_sqft/units for multi-family, total_sqft for SFH
    df["owner_unit_sqft"] = df.apply(
        lambda row: (
            row["owner_unit_sqft"]
            if pd.notna(row["owner_unit_sqft"]) and row["owner_unit_sqft"] > 0
            else (
                row["square_ft"] / row["units"]
                if row["units"] > 0
                else row["square_ft"]
            )
        ),
        axis=1,
    )

    neighborhoods_df = neighborhoods.get_neighborhoods_dataframe(supabase)
    df = df.merge(neighborhoods_df, on="address1", how="left")
    df = apply_calculations_on_dataframe(df=df, loan=LOAN, assumptions=ASSUMPTIONS)
    df = apply_investment_calculations(df=df, loan=LOAN, assumptions=ASSUMPTIONS)
    console.print("[green]Property data reloaded successfully![/green]")


load_assumptions()
load_loan(LAST_USED_LOAN)
reload_dataframe()

def get_all_phase0_qualifying_properties():
    """
    This method filters all properties based on our criteria for financial viability using quick rent estimates:
      - status = 'active'
      - Cash needed must be below $25,000
      - SFH/MF: Monthly total cashflow is above -200
      - Square Feet must be greater than or equal to 1000
    """
    return df.copy().query(PHASE0_CRITERIA).copy()


def get_phase0_qualifiers_lacking_research():
    """
    This method finds all Phase 0 qualifying properties that lack market research required for future phases.
    """
    phase0_df = get_all_phase0_qualifying_properties()
    return phase0_df.query("has_market_research == False")


def get_all_phase1_qualifying_properties():
    """
    This method filters all properties based on our criteria for financial viability using market rent estimates
      - 1% rule (monthly gross rent must be 1% or more of purchase price)
      - 50% rule (operating expenses must be 50% or lower than gross rent)
      - Debt Service Coverage Ratio should be above 1.25
      - Net Present Value in 10 years must be positive, thus beating the stock market
      - SFH/MF: Market Rent Monthly Cashflow Y1 must be above -400
      - SFH: Market Rent Monthly Cashflow Y2 must be above -50
      - MF: Market Rent Monthly Cashflow Y2 must be above 400
    """
    base_df = get_all_phase0_qualifying_properties()
    filtered_df = base_df.query(PHASE1_CRITERIA).copy()
    filtered_df["qualification_type"] = "current"
    qualifier_address1s = filtered_df["address1"].tolist()
    reduced_df = get_reduced_pp_df(0.10)
    reduced_df = reduced_df.query(PHASE0_CRITERIA).query(PHASE1_CRITERIA).copy()
    reduced_df["qualification_type"] = "contingent"
    reduced_df = reduced_df[~reduced_df["address1"].isin(qualifier_address1s)].copy()
    creative_df = get_additional_room_rental_df()
    creative_df = creative_df.query(PHASE0_CRITERIA).query(PHASE1_CRITERIA).copy()
    creative_df["qualification_type"] = "creative"
    return filtered_df, reduced_df, creative_df


def get_combined_phase1_qualifiers():
    current_df, reduced_df, creative_df = get_all_phase1_qualifying_properties()
    combined = pd.concat(
        [current_df, reduced_df, creative_df], ignore_index=True
    ).drop_duplicates(subset=["address1"], keep="first")
    return combined

def get_phase1_research_list():
    """
    Criteria for the research list:
    - Neighborhood letter grade must be C or higher
    - The qualification type must be CURRENT or the property is For Sale Buy Owner
    - Cashflow Year 2 must be above -$50
    """
    combined = get_combined_phase1_qualifiers()
    qualified_df = combined.query(PHASE1_TOUR_CRITERIA).copy()
    qualified_addresses = qualified_df["address1"].tolist()
    unqualified_df = combined[~combined["address1"].isin(qualified_addresses)].copy()
    return qualified_df, unqualified_df

def get_additional_room_rental_df():
    dataframe = df.copy()
    df2 = dataframe.query("min_rent_unit_beds > 1").copy()
    df2["additional_room_rent"] = df2.apply(calculate_additional_room_rent, axis=1)
    df2["total_rent"] = df2["total_rent"] + df2["additional_room_rent"]
    df2["monthly_cash_flow"] = df2["total_rent"] - df2["total_monthly_cost"]
    df2["annual_cash_flow"] = df2["monthly_cash_flow"] * 12
    df2["mr_annual_NOI_y1"] = (
        df2["mr_net_rent_y1"] - df2["mr_operating_expenses"]
    ) * 12
    df2["mr_cap_rate_y1"] = df2["mr_annual_NOI_y1"] / df2["purchase_price"]
    df2["mr_CoC_y1"] = df2["mr_annual_cash_flow_y1"] / df2["cash_needed"]
    df2["mr_GRM_y1"] = df2["purchase_price"] / df2["mr_annual_rent_y1"]
    return df2

def get_reduced_pp_df(reduction_factor):
    dataframe = df.copy()
    dataframe["original_price"] = dataframe["purchase_price"]
    dataframe["purchase_price"] = dataframe["purchase_price"] * (
        1 - reduction_factor
    )  # new purchase price
    dataframe = apply_calculations_on_dataframe(df=dataframe, loan=LOAN, assumptions=ASSUMPTIONS)
    dataframe = apply_investment_calculations(df=dataframe, loan=LOAN, assumptions=ASSUMPTIONS)
    return dataframe

def analyze_property(property_id):
    """Display detailed analysis for a single property"""
    row = df[df["address1"] == property_id].iloc[0]
    property_rents = rents[rents["address1"] == property_id]
    is_single_family = int(row["units"]) == 0

    if property_rents.empty:
        console.print("[red]ERROR: No rent estimates found for this property![/red]")
        console.print(
            "[yellow]This property may need rent estimates to be generated.[/yellow]"
        )
        return

    display_property_overview_panel(console, row)
    display_property_rent_estimates_table(console, property_rents, is_single_family)
    display_property_investment_metrics_table(console, row, is_single_family)
    display_investment_requirements_panel(console, row, ASSUMPTIONS, LOAN)

    while True:
        research_menu_choices = [
            "<- Go back",
            "Edit property assessment",
            "View risk assessment report",
            "View property summary",
            "View closing costs breakdown",
            "Edit neighborhood assessment",
            "Record price change",
            "Change status",
            "Generate new rent research",
            "View existing research reports",
            "Generate rent estimates from report",
            "Scrape neighborhood from FindNeighborhoods.dsm.city",
            "Run neighborhood analysis",
            "Extract neighborhood letter grade",
            "[DANGER] - Delete property",
            "Export property analysis to PDF",
        ]

        if is_single_family:
            research_menu_choices.append("Generate property-wide rent research")

        research_menu_choices.append("Skip - return to main menu")

        research_choice = questionary.select(
            "Would you like to generate or view rental market research for this property?",
            choices=research_menu_choices,
        ).ask()

        if research_choice == "<- Go back":
            break
        elif research_choice == "Edit property assessment":
            edit_property_assessment(property_id, supabase, console)
        elif research_choice == "View risk assessment report":
            handle_risk_assessment(property_id, supabase, console)
        elif research_choice == "View property summary":
            handle_property_summary(property_id, supabase, console, df)
        elif research_choice == "View closing costs breakdown":
            display_closing_costs_table(console, row, LOAN)
        elif research_choice == "Edit neighborhood assessment":
            edit_neighborhood_assessment(property_id, supabase, console)
        elif research_choice == "Generate new rent research":
            handle_rent_research_generation(
                property_id, supabase, console, handle_generate_rent_estimates
            )
        elif research_choice == "View existing research reports":
            handle_view_research_reports(property_id, supabase, console)
        elif research_choice == "Generate rent estimates from report":
            handle_generate_rent_estimates(property_id, supabase, console)
            reload_dataframe()
        elif research_choice == "Generate property-wide rent research":
            handle_property_wide_research_generation(property_id, supabase, console)
            reload_dataframe()
            console.print(
                "\n[bold green]✅ Property-wide rent estimates successfully extracted and saved![/bold green]"
            )
        elif research_choice == "Scrape neighborhood from FindNeighborhoods.dsm.city":
            handle_scrape_neighborhood_from_findneighborhoods(
                property_id, supabase, console, scraper, ask_user=True
            )
            reload_dataframe()
        elif research_choice == "Run neighborhood analysis":
            handle_neighborhood_analysis(property_id, console, neighborhoods)
            reload_dataframe()
        elif research_choice == "Extract neighborhood letter grade":
            handle_extract_neighborhood_grade(property_id, supabase, console, neighborhoods)
            reload_dataframe()
        elif research_choice == "Record price change":
            handle_price_change(property_id, row["purchase_price"], supabase)
            reload_dataframe()
            display_new_property_qualification(
                console, property_id, get_all_phase1_qualifying_properties
            )
        elif research_choice == "Change status":
            handle_status_change(property_id, supabase)
            reload_dataframe()
        elif research_choice == "[DANGER] - Delete property":
            confirm = questionary.confirm("Actually delete this property?").ask()

            if confirm:
                handle_delete_property(property_id, supabase, console)
            else:
                console.print("Phew, glad we caught that", style="yellow")
        elif research_choice == "Export property analysis to PDF":
            downloads_folder = os.getenv("DOWNLOADS_FOLDER", ".")
            safe_address = property_id.replace(" ", "_").replace(",", "").replace(".", "")
            output_path = os.path.join(downloads_folder, f"{safe_address}_analysis.pdf")
            row = df[df["address1"] == property_id].iloc[0]

            loan_info = {
                "interest_rate": LOAN["interest_rate"],
                "apr_rate": LOAN["apr_rate"],
                "down_payment_rate": LOAN["down_payment_rate"],
                "years": LOAN["loan_length_years"],
                "mip_upfront_rate": LOAN["mip_upfront_rate"],
                "mip_annual_rate": LOAN["mip_annual_rate"],
            }

            assumptions_info = {
                "appreciation_rate": ASSUMPTIONS["appreciation_rate"],
                "rent_appreciation_rate": ASSUMPTIONS["rent_appreciation_rate"],
                "property_tax_rate": ASSUMPTIONS["property_tax_rate"],
                "home_insurance_rate": ASSUMPTIONS["home_insurance_rate"],
                "vacancy_rate": ASSUMPTIONS["vacancy_rate"],
                "repair_savings_rate": ASSUMPTIONS["repair_savings_rate"],
                "capex_reserve_rate": ASSUMPTIONS["capex_reserve_rate"],
                "closing_costs_rate": ASSUMPTIONS["closing_costs_rate"],
                "discount_rate": ASSUMPTIONS["discount_rate"],
            }

            result_path = export_property_analysis(
                row,
                rents,
                ASSUMPTIONS["after_tax_monthly_income"],
                loan_info,
                assumptions_info,
                output_path,
            )
            console.print(f"[green]PDF exported successfully to: {result_path}[/green]")


def get_start_screen_summary(df):
    phase0_df = get_all_phase0_qualifying_properties()
    phase0_missing_mr_df = get_phase0_qualifiers_lacking_research()
    current, contingent, creative = get_all_phase1_qualifying_properties()
    phase1_df = get_combined_phase1_qualifiers()
    touring, nontouring = get_phase1_research_list()
    touring_incomplete_assessments_df = is_property_assessment_done_vectorized(df=touring)
    touring_missing_tours = get_properties_missing_tours(supabase, console, touring)

    summary = {}
    summary["properties_count"] = len(df)
    summary["active_properties_count"] = len(df.query("status == 'active'"))
    summary["inactive_properties_count"] = (
        summary["properties_count"] - summary["active_properties_count"]
    )
    summary["phase0_count"] = len(phase0_df)
    summary["phase0_avg_cashflow_qe"] = phase0_df["monthly_cash_flow"].mean()
    summary["phase0_avg_cashflow_y1"] = phase0_df["mr_monthly_cash_flow_y1"].mean()
    summary["phase0_avg_cashflow_y2"] = phase0_df["mr_monthly_cash_flow_y2"].mean()
    summary["phase0_avg_cash_needed"] = phase0_df["cash_needed"].mean()
    summary["phase0_avg_price"] = phase0_df["purchase_price"].mean()
    summary["phase0_missing_mr_count"] = len(phase0_missing_mr_df)
    summary["phase0_missing_mr_list"] = phase0_missing_mr_df["address1"].to_list()
    summary["phase1_cur_count"] = len(current)
    summary["phase1_con_count"] = len(contingent)
    summary["phase1_cre_count"] = len(creative)
    summary["phase1_avg_cashflow_qe"] = phase1_df["monthly_cash_flow"].mean()
    summary["phase1_avg_cashflow_y1"] = phase1_df["mr_monthly_cash_flow_y1"].mean()
    summary["phase1_avg_cashflow_y2"] = phase1_df["mr_monthly_cash_flow_y2"].mean()
    summary["phase1_avg_cash_needed"] = phase1_df["cash_needed"].mean()
    summary["phase1_avg_price"] = phase1_df["purchase_price"].mean()
    summary["phase1_missing_est_price"] = len(phase1_df[phase1_df["est_price"].isnull()])
    summary["phase1_missing_neighborhood"] = len(phase1_df[phase1_df["neighborhood"].isnull()])
    summary["phase1_missing_neighborhood_grade"] = len(phase1_df[phase1_df["neighborhood_letter_grade"].isnull()])
    summary["phase1_missing_neighborhood_niche_grade"] = len(phase1_df[phase1_df["niche_com_letter_grade"].isnull()])
    summary["touring_count"] = len(touring)
    summary["touring_avg_cashflow_qe"] = touring["monthly_cash_flow"].mean()
    summary["touring_avg_cashflow_y1"] = touring["mr_monthly_cash_flow_y1"].mean()
    summary["touring_avg_cashflow_y2"] = touring["mr_monthly_cash_flow_y2"].mean()
    summary["touring_avg_cash_needed"] = touring["cash_needed"].mean()
    summary["touring_avg_price"] = touring["purchase_price"].mean()
    summary["touring_missing_est_value"] = len(touring[touring["est_price"].isnull()])
    summary["touring_missing_assessments_list"] = touring_incomplete_assessments_df["address1"].to_list()
    summary["touring_missing_tours_count"] = len(touring_missing_tours)
    summary["touring_missing_tours_list"] = touring["address1"].to_list()
    summary["nontouring_count"] = len(nontouring)
    summary["phase2_count"] = 0

    return summary

using_application = True

def run_portfolio_options():
    dataframe = df.query("status == 'accepted'")
    display_all_properties(
        properties_df=dataframe,
        df=df,
        title="Properties in our portfolio",
        show_prop_type=True,
        console=console,
    )

def run_all_properties_options():
    using_all_properties = True
    choices = [
        "Phase 0 - Qualifiers",
        "Phase 1 - Qualifiers",
        "Phase 1 - Total Rent Differences",
        "Phase 1.5 - Research List",
        "All properties - Active",
        "All properties - Y2 Calculations",
        "All properties - Property Info",
        "All properties - Investment Metrics",
        "All properties - Sold / Passed",
        "Go back",
    ]

    while using_all_properties:
        option = questionary.select(
            "What would you like to display?", choices=choices
        ).ask()

        if option == "Go back":
            using_all_properties = False
        elif option == "All properties - Active":
            dataframe = df.query("status == 'active'")
            display_all_properties(
                properties_df=dataframe,
                df=df,
                title="All active properties using FHA",
                show_prop_type=True,
                console=console,
            )
        elif option == "Phase 0 - Qualifiers":
            phase0_df = get_all_phase0_qualifying_properties()
            display_all_properties(
                properties_df=phase0_df,
                df=df,
                title="Phase 0 Qualifiers",
                show_prop_type=True,
                console=console,
                show_has_mr=True,
            )
        elif option == "Phase 1 - Qualifiers":
            current, contingent, creative = get_all_phase1_qualifying_properties()
            phase0_df = get_phase0_qualifiers_lacking_research()
            display_all_phase1_qualifying_properties(
                console, df, current, contingent, creative, phase0_df
            )
        elif option == "Phase 1.5 - Research List":
            qualified_df, unqualified_df = get_phase1_research_list()
            display_phase1_research_list(console, qualified_df, unqualified_df)
        elif option == "Phase 1 - Total Rent Differences":
            display_phase1_total_rent_differences(
                console, get_combined_phase1_qualifiers
            )
        elif option == "All properties - Y2 Calculations":
            display_y2_calculations(console, df)
        elif option == "All properties - Property Info":
            display_all_properties_info(console, df, properties_df=df)
        elif option == "All properties - Investment Metrics":
            display_property_metrics(console, df, get_combined_phase1_qualifiers)
        elif option == "All properties - Sold / Passed":
            dataframe = df.query("status != 'active'")
            display_all_properties(
                properties_df=dataframe,
                df=df,
                title="All inactive properties",
                show_status=True,
                console=console,
            )

def run_scripts_options():
    using_scripts = True
    choices = ["Go back", "Add property valuations to all Phase 1.5 qualifiers", "Automate market research for Phase 0 properties", "Add missing neighborhoods"]
    scripts = ScriptsProvider(supabase_client=supabase, console=console, neighborhood_scraper=scraper, neighborhood_client=neighborhoods)

    while using_scripts:
        option = questionary.select("Select a script", choices=choices).ask()
        if option == "Go back":
            using_scripts = False
        elif option == "Add property valuations to all Phase 1.5 qualifiers":
            qualified_df, _ = get_phase1_research_list()
            scripts.run_add_property_values_script(properties_df=qualified_df)
            reload_dataframe()
        elif option == "Add missing neighborhoods":
            scripts.run_add_missing_neighborhoods(properties_df=df)
            reload_dataframe()
        elif option == "Automate market research for Phase 0 properties":
            phase0_lacking_df = get_phase0_qualifiers_lacking_research()

            if len(phase0_lacking_df) == 0:
                console.print("[yellow]No Phase 0 properties lacking research![/yellow]")
            else:
                console.print(f"[cyan]Found {len(phase0_lacking_df)} properties needing research[/cyan]")
                confirm = questionary.confirm(
                    f"Generate market research for all {len(phase0_lacking_df)} properties? This will take ~30-60 seconds per property."
                ).ask()

                if confirm:
                    scripts.run_market_research_automation_script(
                        properties_df=phase0_lacking_df
                    )
                    reload_dataframe()


def run_loans_options():
    using_loans = True
    choices = ["Go back", "Add new loan", "View loans", "Change loans for session"]
    loans_provider = LoansProvider(supabase, console)

    while using_loans:
        option = questionary.select("Select an option", choices=choices).ask()
        if option == "Go back":
            using_loans = False
        elif option == "Add new loan":
            console.print("Let's add a new loan", style="bold blue")
            proceed = False
            while not proceed:
                loan_details = loans_provider.collect_loan_details()
                console.print(
                    Panel(
                        f"Loan Name: {loan_details.name}\n"
                        f"Interest Rate: {loan_details.interest_rate * 100:.2f}%\n"
                        f"APR Rate: {loan_details.apr_rate * 100:.2f}%\n"
                        f"Down Payment: {loan_details.down_payment_rate * 100:.1f}%\n"
                        f"Term: {loan_details.years} years\n"
                        f"MIP Upfront: {loan_details.mip_upfront_rate * 100:.2f}%\n"
                        f"MIP Annual: {loan_details.mip_annual_rate * 100:.2f}%\n"
                        f"Upfront Discounts: ${loan_details.upfront_discounts:,.2f}\n"
                        f"Preapproved Amount: ${loan_details.preapproved_amount:,}\n"
                        f"Expiration Date: {loan_details.expiration_date}",
                        title="Loan Details Review",
                    )
                )
                proceed = questionary.confirm("Does everything look correct?").ask()

                if not proceed:
                    console.print(
                        "Please enter the loan details again", style="bold blue"
                    )
            success = loans_provider.add_loan(loan_details)
            if success:
                console.print("[green]Loan added successfully![/green]")
            else:
                console.print("[red]Failed to add loan[/red]")
        elif option == "View loans":
            loans = loans_provider.get_loans()
            display_loans(console=console, loans=loans)
        elif option == "Change loans for session":
            selected_loan_id = handle_changing_loan(supabase, console)
            LAST_USED_LOAN = selected_loan_id
            load_loan(LAST_USED_LOAN)
            reload_dataframe()

if __name__ == "__main__":
    summary = get_start_screen_summary(df)
    display_start_screen_summary(console, summary)
    while using_application:
        choices = [
            "Portfolio",
            "All properties",
            "One property",
            "One property - phase 1 research list",
            "Add new property",
            "Scripts",
            "Loans",
            "Refresh data",
            "Quit",
        ]
        option = questionary.select(
            "What would you like to analyze?", choices=choices
        ).ask()

        display_current_context_panel(console, LOAN["name"], ASSUMPTIONS["description"])

        if option == "Quit":
            using_application = False
        elif option == "Portfolio":
            run_portfolio_options()
        elif option == "All properties":
            run_all_properties_options()
        elif option == "One property":
            property_ids = []
            properties_get_response = (
                supabase.table("properties").select("address1").limit(10000).execute()
            )
            for row in properties_get_response.data:
                property_ids.append(row["address1"])
            property_id = inquirer.fuzzy(
                message="Type to search properties",
                choices=property_ids,
                default="",
                multiselect=False,
                validate=None,
                invalid_message="Invalid input",
            ).execute()
            analyze_property(property_id)
        elif option == "One property - phase 1 research list":
            tour_list, _ = get_phase1_research_list()
            property_ids = sorted(tour_list["address1"].tolist())  # Sort alphabetically

            if len(property_ids) == 0:
                console.print(
                    "[yellow]No properties on phase 1 research list yet[/yellow]\n"
                )
            else:
                property_id = inquirer.fuzzy(
                    message="Type to search phase 1 research list properties",
                    choices=property_ids,
                    default="",
                    multiselect=False,
                    validate=None,
                    invalid_message="Invalid input",
                ).execute()
                analyze_property(property_id)
        elif option == "Add new property":
            property_details, passes_phase0 = run_add_property(
                supabase_client=supabase,
                reload_df_callback=reload_dataframe,
                get_all_phase0_qualifying_properties=get_all_phase0_qualifying_properties,
                get_reduced_pp_df=get_reduced_pp_df,
                phase0_criteria=PHASE0_CRITERIA,
            )
            if property_details is None:
                console.print(
                    "[red]Property addition failed, skipping post-processing[/red]"
                )
            else:
                handle_scrape_neighborhood_from_findneighborhoods(
                    property_details["address1"],
                    supabase,
                    console,
                    scraper,
                    ask_user=False,
                )

                if passes_phase0:
                    handle_rent_research_after_add(
                        property_details["address1"], supabase, console, ask_user=False
                    )
                    reload_dataframe()
                    display_new_property_qualification(
                        console,
                        property_details["address1"],
                        get_all_phase1_qualifying_properties,
                    )
        elif option == "Scripts":
            run_scripts_options()
        elif option == "Loans":
            run_loans_options()
        elif option == "Refresh data":
            load_assumptions()
            load_loan(LAST_USED_LOAN)
            reload_dataframe()

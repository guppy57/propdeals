from rich.table import Table
from helpers import (
    format_currency,
    format_number,
    format_percentage,
    calculate_additional_room_rent,
)

def display_all_properties(
    console,
    df,
    properties_df,
    title,
    show_status=False,
    show_min_rent_data=False,
    show_prop_type=False,
    sort_by="units",
):
    dataframe = df if properties_df is None else properties_df
    if sort_by == "units":
        dataframe = dataframe.sort_values(by="units")
    elif sort_by == "y2_cf":
        dataframe = dataframe.sort_values(by="monthly_cash_flow_y2")
    table = Table(title=title, show_header=True, header_style="bold magenta")
    mobility_75th_percentile = df["mobility_score"].quantile(0.75)
    mobility_25th_percentile = df["mobility_score"].quantile(0.25)
    forecast_10y_75th_percentile = df["10y_forecast"].quantile(0.75)
    forecast_10y_25th_percentile = df["10y_forecast"].quantile(0.25)
    irr_10yr_75th_percentile = df["irr_10yr"].quantile(0.75)
    irr_10yr_25th_percentile = df["irr_10yr"].quantile(0.25)
    price_20th = dataframe["purchase_price"].quantile(0.20)
    price_40th = dataframe["purchase_price"].quantile(0.40)
    price_60th = dataframe["purchase_price"].quantile(0.60)
    price_80th = dataframe["purchase_price"].quantile(0.80)
    cash_20th = dataframe["cash_needed"].quantile(0.20)
    cash_40th = dataframe["cash_needed"].quantile(0.40)
    cash_60th = dataframe["cash_needed"].quantile(0.60)
    cash_80th = dataframe["cash_needed"].quantile(0.80)
    costs_to_income_75th_percentile = dataframe["costs_to_income"].quantile(0.75)
    costs_to_income_25th_percentile = dataframe["costs_to_income"].quantile(0.25)

    def get_quintile_color(value, p20, p40, p60, p80):
        """Return color based on quintile position (lower values = better = greener)"""
        if value <= p20:
            return "bright_green"
        elif value <= p40:
            return "green"
        elif value <= p60:
            return "yellow"
        elif value <= p80:
            return "orange3"
        else:
            return "red"

    table.add_column(f"Property ({len(properties_df)})", style="cyan", no_wrap=True)

    if show_prop_type:
        table.add_column("Type", justify="right", style="bold white")

    table.add_column("Price", justify="right", no_wrap=True)
    table.add_column("Cash Needed", justify="right")
    table.add_column("Costs/mo", justify="right", style="yellow")
    table.add_column("CF/mo Y1", justify="right", no_wrap=True)
    table.add_column("CF/mo Y2", justify="right", no_wrap=True)
    # table.add_column("NOI Y2", justify="right", style="yellow")
    # table.add_column("CapR Y1", justify="right", style="blue")
    # table.add_column("CapR Y2", justify="right", style="blue")
    # table.add_column("CoC Y2", justify="right", style="purple")
    # table.add_column("1% Rule", justify="right", style="cyan")
    # table.add_column("50% Rule", justify="right", style="magenta")
    # table.add_column("DSCR", justify="right", style="blue")
    table.add_column("Cost/Inc", justify="right", style="bold white")
    # table.add_column("DS", justify="right", style="bold white")  # deal score
    # table.add_column("MS", justify="right", style="bold white")  # mobility score
    # table.add_column("10Y", justify="right", style="bold white")  # 10 year investment growth
    table.add_column("IRR 10Y", justify="right", style="bold white")
    # table.add_column("NPV10Y", justify="right", style="bold white") # Net present value 10 years

    if show_status:
        table.add_column("Status", justify="right", style="bold white")

    if show_min_rent_data:
        table.add_column("MinR Unit Beds", justify="right", style="bold white")
        table.add_column("Add. Beds", justify="right", style="bold white")
        table.add_column("Add. Rent", justify="right", style="bold white")

    for _, row in dataframe.iterrows():
        cf_y1_style = "red" if row["monthly_cash_flow_y1"] < 0 else "green"
        cf_y2_style = "red" if row["monthly_cash_flow_y2"] < 0 else "green"

        noi_style = "red" if row["monthly_NOI_y2"] < 0 else "green"

        opex_rent_style = (
            "green"
            if 0.45 <= row["OpEx_Rent"] <= 0.55
            else ("yellow" if 0.35 <= row["OpEx_Rent"] <= 0.65 else "red")
        )
        dscr_style = "green" if row["DSCR"] >= 1.25 else "red"
        mgr_pp_style = "green" if row["MGR_PP"] >= 0.01 else "red"

        mobility_score_style = (
            "green"
            if row["mobility_score"] >= mobility_75th_percentile
            else (
                "yellow" if row["mobility_score"] >= mobility_25th_percentile else "red"
            )
        )

        forecast_10y_style = (
            "green"
            if row["10y_forecast"] >= forecast_10y_75th_percentile
            else (
                "yellow"
                if row["10y_forecast"] >= forecast_10y_25th_percentile
                else "red"
            )
        )

        irr_10yr_style = (
            "green"
            if row["irr_10yr"] >= irr_10yr_75th_percentile
            else ("yellow" if row["irr_10yr"] >= irr_10yr_25th_percentile else "red")
        )

        price_style = get_quintile_color(
            row["purchase_price"], price_20th, price_40th, price_60th, price_80th
        )
        cash_style = get_quintile_color(
            row["cash_needed"], cash_20th, cash_40th, cash_60th, cash_80th
        )

        costs_to_income_style = (
            "green"
            if row["costs_to_income"] <= costs_to_income_25th_percentile
            else (
                "yellow"
                if row["costs_to_income"] <= costs_to_income_75th_percentile
                else "red"
            )
        )

        npv_style = "red" if row["npv_10yr"] <= 0 else "green"

        prop_types = {0: "SFH", 2: "2PX", 3: "3PX", 4: "4PX"}
        prop_type_styles = {0: "yellow", 2: "red", 3: "blue", 4: "green"}

        row_args = [str(row["address1"])]

        if show_prop_type:
            pt_style = prop_type_styles[row["units"]]
            row_args.append(f"[{pt_style}]{prop_types[row['units']]}[/{pt_style}]")

        row_args.extend(
            [
                f"[{price_style}]{format_currency(row['purchase_price'])}[/{price_style}]",
                f"[{cash_style}]{format_currency(row['cash_needed'])}[/{cash_style}]",
                format_currency(row["total_monthly_cost_y2"]),
                f"[{cf_y1_style}]{format_currency(row['monthly_cash_flow_y1'])}[/{cf_y1_style}]",
                f"[{cf_y2_style}]{format_currency(row['monthly_cash_flow_y2'])}[/{cf_y2_style}]",
                # f"[{noi_style}]{format_currency(row['monthly_NOI_y2'])}[/{noi_style}]",
                # format_percentage(row["cap_rate_y1"]),
                # format_percentage(row["cap_rate_y2"]),
                # format_percentage(row["CoC_y2"]),
                # f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]",
                # f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]",
                # f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]",
                f"[{costs_to_income_style}]{format_percentage(row['costs_to_income'])}[/{costs_to_income_style}]",
                # f"[{mobility_score_style}]{int(row['mobility_score'])}[/{mobility_score_style}]",
                # f"[{forecast_10y_style}]{format_currency(row['10y_forecast'])}[/{forecast_10y_style}]",
                f"[{irr_10yr_style}]{format_percentage(row['irr_10yr'])}[/{irr_10yr_style}]",
                # f"[{npv_style}]{format_currency(row["npv_10yr"])}[/{npv_style}]"
            ]
        )

        if show_status:
            row_args.append(row["status"])

        if show_min_rent_data:
            row_args.append(str(row["min_rent_unit_beds"]))
            row_args.append(str(int(row["min_rent_unit_beds"] - 1)))
            row_args.append(str(calculate_additional_room_rent(row)))

        table.add_row(*row_args)

    console.print(table)

import questionary
from datetime import date, datetime, timedelta
from rich.console import Console
from rich.panel import Panel
from supabase import Client

from editor import edit_multiline_text


# Field configuration: maps user-friendly label to (db_field_name, field_type)
FIELD_CONFIG = {
    # County Records
    "Obtained county records": ("obtained_county_records", "boolean"),
    "County record notes": ("county_record_notes", "editor"),
    "Historical Turnover Rate": ("historical_turnover_rate", "float"),
    "Average Ownership Duration": ("average_ownership_duration", "float"),

    # Restrictions
    "Has deed restrictions": ("has_deed_restrictions", "boolean"),
    "Has HOA": ("has_hao", "boolean"),
    "Has historic preservation": ("has_historic_preservation", "boolean"),

    # Property Details
    "Setbacks": ("setbacks", "editor"),
    "Has easements": ("has_easements", "boolean"),
    "Easements": ("easements", "editor"),
    "In flood zone": ("in_flood_zone", "boolean"),
    "Year Built": ("built_in", "integer"),
    "Zillow Link": ("zillow_link", "text"),
    "Days in Market": ("listed_date", "days_to_date"),

    # Permits
    "Has open/pulled permits": ("has_open_pulled_permits", "boolean"),
    "Has work done without permits": ("has_work_done_wo_permits", "boolean"),
    "Permit notes": ("permit_notes", "editor"),

    # Purchase History
    "Last purchase price": ("last_purchase_price", "float"),
    "Last purchase date": ("last_purchase_date", "date"),

    # Other Notes
    "Whitepages notes": ("whitepages_notes", "editor"),
}


def handle_editor_field(field_label: str, field_name: str, current_value: str, console: Console):
    """Handle text editor fields"""
    console.print(f"[cyan]Opening editor for {field_label}... (save and quit to continue)[/cyan]")

    try:
        new_value = edit_multiline_text(current_value or "", field_label)
    except Exception as e:
        console.print(f"[red]Error opening editor: {str(e)}[/red]")
        return None

    # Show preview of changes
    console.print("\n" + "="*50)
    console.print("[yellow]BEFORE:[/yellow]")
    console.print(current_value if current_value else "[dim](empty)[/dim]")
    console.print("\n[green]AFTER:[/green]")
    console.print(new_value if new_value else "[dim](empty)[/dim]")
    console.print("="*50 + "\n")

    return new_value if new_value else None


def handle_boolean_field(field_label: str, field_name: str, current_value: bool, console: Console):
    """Handle boolean fields"""
    current_display = "Yes" if current_value else "No" if current_value is False else "Not set"

    new_value = questionary.confirm(
        f"{field_label} (currently: {current_display})",
        default=current_value if current_value is not None else False
    ).ask()

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_display}")
    console.print(f"[green]New:[/green] {'Yes' if new_value else 'No'}\n")

    return new_value


def handle_integer_field(field_label: str, field_name: str, current_value: int, console: Console):
    """Handle integer fields"""
    default_str = str(current_value) if current_value is not None else ""

    new_value_str = questionary.text(
        f"{field_label} (currently: {current_value if current_value is not None else 'Not set'})",
        default=default_str,
        validate=lambda x: x == "" or x.isdigit()
    ).ask()

    if new_value_str == "":
        new_value = None
    else:
        new_value = int(new_value_str)

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_value if current_value is not None else 'Not set'}")
    console.print(f"[green]New:[/green] {new_value if new_value is not None else 'Not set'}\n")

    return new_value


def handle_float_field(field_label: str, field_name: str, current_value: float, console: Console):
    """Handle float/double precision fields"""
    default_str = str(current_value) if current_value is not None else ""

    def validate_float(text):
        if text == "":
            return True
        try:
            float(text)
            return True
        except ValueError:
            return False

    new_value_str = questionary.text(
        f"{field_label} (currently: {current_value if current_value is not None else 'Not set'})",
        default=default_str,
        validate=validate_float
    ).ask()

    if new_value_str == "":
        new_value = None
    else:
        new_value = float(new_value_str)

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_value if current_value is not None else 'Not set'}")
    console.print(f"[green]New:[/green] {new_value if new_value is not None else 'Not set'}\n")

    return new_value


def handle_date_field(field_label: str, field_name: str, current_value: str, console: Console):
    """Handle date fields (YYYY-MM-DD format)"""
    default_str = str(current_value) if current_value is not None else ""

    def validate_date(text):
        if text == "":
            return True
        # Basic validation for YYYY-MM-DD format
        parts = text.split('-')
        if len(parts) != 3:
            return False
        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            # Basic range checks
            if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
                return False
            return True
        except ValueError:
            return False

    new_value_str = questionary.text(
        f"{field_label} (YYYY-MM-DD) (currently: {current_value if current_value is not None else 'Not set'})",
        default=default_str,
        validate=validate_date
    ).ask()

    new_value = new_value_str if new_value_str else None

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_value if current_value is not None else 'Not set'}")
    console.print(f"[green]New:[/green] {new_value if new_value is not None else 'Not set'}\n")

    return new_value


def handle_text_field(field_label: str, field_name: str, current_value: str, console: Console):
    """Handle single-line text fields"""
    default_str = str(current_value) if current_value is not None else ""

    new_value_str = questionary.text(
        f"{field_label} (currently: {current_value if current_value else 'Not set'})",
        default=default_str
    ).ask()

    new_value = new_value_str if new_value_str else None

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_value if current_value else 'Not set'}")
    console.print(f"[green]New:[/green] {new_value if new_value else 'Not set'}\n")

    return new_value


def handle_days_to_date_field(field_label: str, field_name: str, current_value: str, console: Console):
    """Handle days-to-date conversion fields (accepts days in market, stores as date)"""
    # Calculate current days in market if date exists
    current_days = None
    current_display = "Not set"

    if current_value:
        try:
            # Parse the date string
            if isinstance(current_value, str):
                listed_datetime = datetime.fromisoformat(current_value.replace('Z', '+00:00').split('T')[0])
            else:
                listed_datetime = datetime.fromisoformat(str(current_value))

            # Calculate days in market
            current_days = (datetime.now() - listed_datetime).days
            current_display = f"{current_days} days (listed on {listed_datetime.date()})"
        except (ValueError, AttributeError):
            current_display = f"Invalid date: {current_value}"

    default_str = str(current_days) if current_days is not None else ""

    def validate_integer(text):
        if text == "":
            return True
        return text.isdigit()

    new_value_str = questionary.text(
        f"{field_label} (enter days in market) (currently: {current_display})",
        default=default_str,
        validate=validate_integer
    ).ask()

    if new_value_str == "":
        new_value = None
    else:
        # Convert days to date: today - days_input = listing_date
        days_in_market = int(new_value_str)
        listing_date = date.today() - timedelta(days=days_in_market)
        new_value = listing_date.isoformat()

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_display}")
    if new_value:
        new_days = int(new_value_str)
        console.print(f"[green]New:[/green] {new_days} days in market (listing date: {new_value})")
    else:
        console.print(f"[green]New:[/green] Not set")
    console.print()

    return new_value


def edit_property_assessment(property_id: str, supabase_client: Client, console: Console):
    """
    Edit property assessment fields using appropriate input methods.

    Args:
        property_id: The address1 of the property to edit
        supabase_client: Supabase client instance
        console: Rich console instance for formatted output
    """
    while True:
        # Fetch current property data first (so we can show checkmarks)
        try:
            response = supabase_client.table("properties").select("*").eq("address1", property_id).single().execute()
            current_data = response.data
        except Exception as e:
            console.print(f"[red]Error fetching property data: {str(e)}[/red]")
            break

        # Build menu with checkmarks for fields that have values
        display_choices = []
        label_to_field = {}  # Map display label back to actual field label

        for field_label in FIELD_CONFIG.keys():
            field_name, field_type = FIELD_CONFIG[field_label]
            current_value = current_data.get(field_name)

            # Determine if field has a value
            has_value = False
            if current_value is not None:
                # Empty strings count as null
                if isinstance(current_value, str):
                    has_value = bool(current_value.strip())
                else:
                    has_value = True

            # Add checkmark or spacing
            indicator = "✓ " if has_value else "  "
            display_label = f"{indicator}{field_label}"
            display_choices.append(display_label)
            label_to_field[display_label] = field_label

        display_choices.append("Go Back")

        field_choice_display = questionary.select(
            "Which field would you like to edit?",
            choices=display_choices
        ).ask()

        if field_choice_display == "Go Back":
            break

        # Get the actual field label (strip indicator)
        field_choice = label_to_field[field_choice_display]

        # Get field configuration
        field_name, field_type = FIELD_CONFIG[field_choice]
        current_value = current_data.get(field_name)

        # Handle the field based on its type
        new_value = None

        if field_type == "editor":
            new_value = handle_editor_field(field_choice, field_name, current_value, console)
        elif field_type == "boolean":
            new_value = handle_boolean_field(field_choice, field_name, current_value, console)
        elif field_type == "integer":
            new_value = handle_integer_field(field_choice, field_name, current_value, console)
        elif field_type == "float":
            new_value = handle_float_field(field_choice, field_name, current_value, console)
        elif field_type == "date":
            new_value = handle_date_field(field_choice, field_name, current_value, console)
        elif field_type == "text":
            new_value = handle_text_field(field_choice, field_name, current_value, console)
        elif field_type == "days_to_date":
            new_value = handle_days_to_date_field(field_choice, field_name, current_value, console)
        else:
            console.print(f"[red]Unknown field type: {field_type}[/red]")
            continue

        # If handling returned None (e.g., error occurred), skip save
        if new_value is None and field_type == "editor":
            continue

        # Confirm the change
        if questionary.confirm("Save this change to the database?").ask():
            try:
                update_response = supabase_client.table("properties").update({
                    field_name: new_value
                }).eq("address1", property_id).execute()

                if hasattr(update_response, "data"):
                    console.print(f"[green]✓ Successfully updated {field_choice}[/green]")
                else:
                    console.print("[yellow]Update completed but response has no 'data' attribute[/yellow]")
            except Exception as e:
                console.print(f"[red]Error updating property: {str(e)}[/red]")
        else:
            console.print("[yellow]Change not saved[/yellow]")

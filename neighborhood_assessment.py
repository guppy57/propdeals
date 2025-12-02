import questionary
from rich.console import Console
from supabase import Client

from editor import edit_multiline_text


# Field configuration: maps user-friendly label to (db_field_name, field_type)
FIELD_CONFIG = {
    # Basic Info
    "School district name": ("school_district_name", "text"),

    # Safety
    "Number of sex offenders within 2 miles": ("num_sex_off_2m", "integer"),

    # School Ratings
    "Elementary school rating": ("elementary_school_rating", "float"),
    "Middle school rating": ("middle_school_rating", "float"),
    "High school rating": ("high_school_rating", "float"),

    # Notes
    "Neighborhood stakeout notes": ("neighborhood_stakeout_notes", "editor"),
    "Talking to neighbors notes": ("talking_neighbor_notes", "editor"),
    "AI neighborhood notes": ("ai_neighborhood_notes", "editor"),
}


def handle_text_field(field_label: str, field_name: str, current_value: str, console: Console):
    """Handle single-line text fields"""
    default_str = str(current_value) if current_value is not None else ""

    new_value = questionary.text(
        f"{field_label} (currently: {current_value if current_value is not None else 'Not set'})",
        default=default_str
    ).ask()

    new_value = new_value if new_value else None

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_value if current_value is not None else 'Not set'}")
    console.print(f"[green]New:[/green] {new_value if new_value is not None else 'Not set'}\n")

    return new_value


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


def edit_neighborhood_assessment(property_id: str, supabase_client: Client, console: Console):
    """
    Edit neighborhood assessment fields using appropriate input methods.
    Auto-creates assessment record if it doesn't exist.

    Args:
        property_id: The address1 of the property
        supabase_client: Supabase client instance
        console: Rich console instance for formatted output
    """
    while True:
        # Fetch or create neighborhood assessment
        try:
            response = supabase_client.table("neighborhood_assessment").select("*").eq("address1", property_id).execute()

            if not response.data or len(response.data) == 0:
                # Create new assessment if it doesn't exist
                console.print("[cyan]No neighborhood assessment found. Creating one...[/cyan]")
                create_response = supabase_client.table("neighborhood_assessment").insert({
                    "address1": property_id
                }).execute()

                if not create_response.data or len(create_response.data) == 0:
                    console.print("[red]Failed to create neighborhood assessment[/red]")
                    break

                current_data = create_response.data[0]
                console.print("[green]✓ Neighborhood assessment created[/green]\n")
            else:
                current_data = response.data[0]

        except Exception as e:
            console.print(f"[red]Error fetching/creating neighborhood assessment: {str(e)}[/red]")
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

        if field_type == "text":
            new_value = handle_text_field(field_choice, field_name, current_value, console)
        elif field_type == "editor":
            new_value = handle_editor_field(field_choice, field_name, current_value, console)
        elif field_type == "integer":
            new_value = handle_integer_field(field_choice, field_name, current_value, console)
        elif field_type == "float":
            new_value = handle_float_field(field_choice, field_name, current_value, console)
        else:
            console.print(f"[red]Unknown field type: {field_type}[/red]")
            continue

        # If handling returned None (e.g., error occurred), skip save
        if new_value is None and field_type == "editor":
            continue

        # Confirm the change
        if questionary.confirm("Save this change to the database?").ask():
            try:
                assessment_id = current_data.get("id")
                update_response = supabase_client.table("neighborhood_assessment").update({
                    field_name: new_value
                }).eq("id", assessment_id).execute()

                if hasattr(update_response, "data"):
                    console.print(f"[green]✓ Successfully updated {field_choice}[/green]")
                else:
                    console.print("[yellow]Update completed but response has no 'data' attribute[/yellow]")
            except Exception as e:
                console.print(f"[red]Error updating neighborhood assessment: {str(e)}[/red]")
        else:
            console.print("[yellow]Change not saved[/yellow]")

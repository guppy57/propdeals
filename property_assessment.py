import questionary
from rich.console import Console
from rich.panel import Panel
from supabase import Client

from editor import edit_multiline_text


def edit_property_assessment(property_id: str, supabase_client: Client, console: Console):
    """
    Edit property assessment fields using a text editor.

    Args:
        property_id: The address1 of the property to edit
        supabase_client: Supabase client instance
        console: Rich console instance for formatted output
    """
    while True:
        # Menu of editable fields
        field_choices = [
            "Whitepages notes",
            "Go Back"
        ]

        field_choice = questionary.select(
            "Which field would you like to edit?",
            choices=field_choices
        ).ask()

        if field_choice == "Go Back":
            break

        # Fetch current property data
        try:
            response = supabase_client.table("properties").select("*").eq("address1", property_id).single().execute()
            current_data = response.data
        except Exception as e:
            console.print(f"[red]Error fetching property data: {str(e)}[/red]")
            continue

        # Handle the selected field
        if field_choice == "Whitepages notes":
            field_name = "whitepages_notes"
            current_value = current_data.get(field_name) or ""

            console.print(f"[cyan]Opening editor for {field_choice}... (save and quit to continue)[/cyan]")

            # Open editor for user to edit text
            try:
                new_value = edit_multiline_text(current_value, field_choice)
            except Exception as e:
                console.print(f"[red]Error opening editor: {str(e)}[/red]")
                continue

            # Show preview of changes
            console.print("\n" + "="*50)
            console.print("[yellow]BEFORE:[/yellow]")
            console.print(current_value if current_value else "[dim](empty)[/dim]")
            console.print("\n[green]AFTER:[/green]")
            console.print(new_value if new_value else "[dim](empty)[/dim]")
            console.print("="*50 + "\n")

            # Confirm the change
            if questionary.confirm("Save this change to the database?").ask():
                try:
                    update_response = supabase_client.table("properties").update({
                        field_name: new_value if new_value else None
                    }).eq("address1", property_id).execute()

                    if hasattr(update_response, "data"):
                        console.print(f"[green]✓ Successfully updated {field_choice}[/green]")
                    else:
                        console.print("[yellow]Update completed but response has no 'data' attribute[/yellow]")
                except Exception as e:
                    console.print(f"[red]Error updating property: {str(e)}[/red]")
            else:
                console.print("[yellow]Change not saved[/yellow]")

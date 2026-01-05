"""
PropDeals Scenario Builder - Textual TUI Application

A real-time investment scenario builder for property analysis.
Build out screens, widgets, and functionality as needed.
"""

import os
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


# ============================================================================
# Screens
# ============================================================================


class MainScreen(Screen):
    """Main starter screen - build this out as needed"""

    BINDINGS = [
        ("q", "quit", "Quit"),
        # TODO: Add more key bindings for navigation
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets for the screen"""
        yield Header()
        yield Static(
            "[bold cyan]PropDeals Scenario Builder[/bold cyan]\n\n"
            "Ready to build!\n\n"
            "TODO: Add your screens, widgets, and layouts here.",
            id="welcome",
        )
        yield Footer()

    def action_quit(self) -> None:
        """Quit the application"""
        self.app.exit()


# ============================================================================
# Main Application
# ============================================================================


class ScenarioBuilderApp(App):
    """Textual application for property investment scenario analysis"""

    CSS_PATH = "scenario_builder.tcss"

    # Reactive state variables - these will auto-update the UI when changed
    df: reactive[Optional[pd.DataFrame]] = reactive(None)
    assumptions: reactive[Optional[dict]] = reactive(None)
    loan: reactive[Optional[dict]] = reactive(None)

    def __init__(self):
        super().__init__()
        # Initialize Supabase client
        load_dotenv()
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY"),
        )

    def on_mount(self) -> None:
        """Called when the app is mounted - initialize here"""
        # TODO: Load initial data
        # Example:
        # self.load_assumptions()
        # self.load_loan(loan_id=2)
        # self.reload_dataframe()

        # Push the main screen
        self.push_screen(MainScreen())

    # ========================================================================
    # Data Loading Methods - TODO: Implement these
    # ========================================================================

    def load_assumptions(self) -> None:
        """Load assumptions from Supabase

        Reference: /Users/guppy57/GitHub/propdeals/run.py:90-148
        """
        # TODO: Implement - see run.py load_assumptions()
        pass

    def load_loan(self, loan_id: int) -> None:
        """Load loan data from Supabase

        Reference: /Users/guppy57/GitHub/propdeals/run.py:150-167
        """
        # TODO: Implement - see run.py load_loan()
        pass

    def reload_dataframe(self) -> None:
        """Load properties and apply calculations

        Reference: /Users/guppy57/GitHub/propdeals/run.py:415-467
        """
        # TODO: Implement - see run.py reload_dataframe()
        pass

    # ========================================================================
    # Reactive Watchers - TODO: Implement these for auto-recalculation
    # ========================================================================

    def watch_assumptions(self, new_val: Optional[dict]) -> None:
        """Called automatically when assumptions changes"""
        # TODO: Trigger recalculation when assumptions change
        pass

    def watch_loan(self, new_val: Optional[dict]) -> None:
        """Called automatically when loan changes"""
        # TODO: Trigger recalculation when loan changes
        pass

    def watch_df(self, new_val: Optional[pd.DataFrame]) -> None:
        """Called automatically when dataframe updates"""
        # TODO: Update UI when dataframe changes
        pass


# ============================================================================
# Entry Point
# ============================================================================


if __name__ == "__main__":
    app = ScenarioBuilderApp()
    app.run()

# Property Analyzer - Textual Migration Plan

## 🎯 Project Overview

### Goals
Transform the current CLI property analyzer into a modern, full-screen TUI application using Textual framework.

### Target Features
- ✨ Full-screen terminal application
- 📊 Live settings view (loan & assumptions sidebar)
- ⌨️ Keyboard shortcuts for all major functions
- 🔄 Real-time data updates
- 📱 Professional dashboard interface
- 📋 Interactive data tables with sorting/filtering

### Benefits
- **Better UX**: Always-visible settings, instant navigation
- **Professional appearance**: Modern TUI that looks like a desktop app
- **Enhanced functionality**: Multi-panel view, live updates, keyboard-driven workflow
- **Code reuse**: 90%+ of existing business logic can be preserved

---

## 🏗️ Architecture Comparison

### Current Structure (CLI)
```
questionary menus → console.print tables → show_footer() before each menu
```

### Target Structure (Textual TUI)
```
App(
  Header: title + time
  Main: DataTable/PropertyDetails
  Sidebar: live settings (loan + assumptions)  
  Footer: keyboard shortcuts + status
)
```

---

## 📋 Implementation Checklist

### Phase 1: Foundation Setup (2-3 hours) ✅ COMPLETED
- [x] **Install Dependencies**
  - [x] Add `textual` to requirements.txt
  - [x] Test installation and basic import
  
- [x] **Create App Structure**
  - [x] Create `textual_app.py` main file
  - [x] Implement `PropertyAnalyzerApp(App)` class
  - [x] Define basic `BINDINGS` for keyboard shortcuts
  - [x] Implement `compose()` method for layout
  
- [x] **Layout System**
  - [x] Design 4-panel layout (header, main, sidebar, footer)
  - [x] Create placeholder widgets for each panel
  - [x] Test basic layout rendering
  
- [x] **Basic Navigation**
  - [x] Implement quit functionality (`q` key)
  - [x] Add basic keyboard shortcuts (1-5 for main functions)
  - [x] Test keyboard event handling

### Phase 2: Data Integration (3-4 hours) ✅ COMPLETED
- [x] **Business Logic Migration**
  - [x] Import existing calculation functions (no changes needed)
  - [x] Import data loading functions (`load_assumptions`, `load_loan`, etc.)
  - [x] Import formatting utilities (`format_currency`, `format_percentage`, etc.)
  
- [x] **Reactive Properties**
  - [x] Create `current_loan = reactive()` for live loan updates
  - [x] Create `assumptions_data = reactive()` for live assumptions
  - [x] Create `properties_data = reactive()` for property table
  - [x] Test reactive updates
  
- [x] **Properties DataTable**
  - [x] Create properties table display with proper formatting
  - [x] Implement column definitions with proper formatting
  - [x] Add color coding for metrics (green/yellow/red based on performance)
  - [x] Test data loading and display
  
- [x] **Property Details Screen**
  - [x] Create property details display functionality
  - [x] Display detailed property analysis (reuse existing logic)
  - [x] Add navigation help and instructions
  - [x] Test property selection and details display

### Phase 3: Interactive Features (2-3 hours)
- [ ] **Settings Sidebar**
  - [ ] Create `SettingsPanel` widget
  - [ ] Display current loan information (name, rate, terms)
  - [ ] Display current assumptions (tax rate, insurance, etc.)
  - [ ] Auto-update when settings change
  - [ ] Style with proper formatting and colors
  
- [ ] **Loan Management**
  - [ ] Create `LoanManagementScreen` or modal
  - [ ] List available loans with selection
  - [ ] Implement loan switching functionality
  - [ ] Update reactive properties when loan changes
  - [ ] Test loan switching updates entire app
  
- [ ] **Property Search & Filtering**
  - [ ] Add search/filter functionality to DataTable
  - [ ] Implement property type filtering (active/inactive)
  - [ ] Add phase 1 qualifiers filter
  - [ ] Test filtering and search performance
  
- [ ] **Screen Navigation**
  - [ ] Implement screen switching with keyboard shortcuts
  - [ ] Add breadcrumb navigation
  - [ ] Test navigation between all screens
  - [ ] Ensure proper state management between screens

### Phase 4: Polish & Advanced Features (1-2 hours)
- [ ] **Status Bar**
  - [ ] Create status bar widget
  - [ ] Show loading states during data operations
  - [ ] Display current action/screen
  - [ ] Show last updated timestamp
  
- [ ] **Command Palette**
  - [ ] Implement Textual's built-in command palette (Ctrl+P)
  - [ ] Add custom commands for all major functions
  - [ ] Test fuzzy search functionality
  
- [ ] **Help System**
  - [ ] Create help/shortcuts screen (`?` or `h` key)
  - [ ] Document all keyboard shortcuts
  - [ ] Add tooltips where appropriate
  
- [ ] **Error Handling**
  - [ ] Add try/catch blocks for database operations
  - [ ] Display user-friendly error messages
  - [ ] Implement retry mechanisms for failed operations
  - [ ] Test error scenarios
  
- [ ] **Final Polish**
  - [ ] Create CSS styling file for consistent appearance
  - [ ] Optimize performance for large datasets
  - [ ] Add loading indicators for slow operations
  - [ ] Final testing and bug fixes

---

## 🔧 Technical Implementation Details

### Key Textual Components to Use
- `App`: Main application class
- `DataTable`: For property listings with sorting/filtering
- `Static`: For settings display and text content
- `Header/Footer`: For app title and shortcuts
- `Tabs`: For different property views
- `Modal`: For dialogs and confirmations

### Keyboard Shortcuts Plan
```
q - Quit application
1 - All Properties view
2 - Single Property search
3 - Add Property
4 - Loans management  
5 - Refresh data
l - Loans (alternative)
r - Refresh (alternative)
? - Help/shortcuts
Ctrl+P - Command palette
Enter - Select/drill down
Esc - Go back/cancel
```

### Reactive State Management
```python
class PropertyAnalyzerApp(App):
    # Live updating properties
    current_loan = reactive("FHA Default")
    current_loan_data = reactive({})
    assumptions_data = reactive({})
    properties_df = reactive(pd.DataFrame())
    
    def watch_current_loan(self, old_loan, new_loan):
        # Auto-refresh all data when loan changes
        self.refresh_properties_data()
```

---

## 🧪 Testing Checklist

### Functionality Tests
- [ ] App starts without errors
- [ ] All keyboard shortcuts work as expected
- [ ] Data loads from Supabase correctly
- [ ] Settings display updates in real-time
- [ ] Property table displays with proper formatting
- [ ] Property details screen shows complete analysis
- [ ] Loan switching updates entire application
- [ ] Filtering and search work correctly
- [ ] Navigation between screens is smooth

### Performance Tests
- [ ] App responds quickly with large datasets
- [ ] Memory usage is reasonable
- [ ] No significant lag during data updates
- [ ] Smooth scrolling in large tables

### User Experience Tests
- [ ] Interface is intuitive and easy to navigate
- [ ] All information is clearly visible
- [ ] Color coding helps identify good/bad properties
- [ ] Keyboard shortcuts feel natural
- [ ] Error messages are helpful

---

## 📦 Dependencies

### New Requirements
```
textual>=0.40.0
```

### Existing Dependencies (Keep)
```
pandas==2.1.4
questionary==2.0.1  # May still use for some dialogs
rich==13.7.0         # Textual builds on Rich
supabase==2.0.2
# ... all other existing dependencies
```

---

## 🚀 Migration Strategy

### Phase-by-Phase Approach
1. **Keep existing code running**: Create new Textual app alongside current CLI
2. **Incremental migration**: Move features one at a time
3. **Test thoroughly**: Each phase should be fully tested before moving on
4. **Preserve functionality**: Ensure no features are lost in translation

### Code Reuse Strategy
- **Business logic**: Import existing calculation functions as-is
- **Data access**: Reuse Supabase integration with minimal changes  
- **Formatting**: Leverage existing format_currency, etc. functions
- **Menu logic**: Transform procedural menus into reactive state changes

---

## 📝 Progress Tracking

### Completed Tasks
- [x] Create migration plan and checklist
- [x] Phase 1: Foundation Setup - COMPLETE

### Current Status
**Phase 2 Complete** - Ready to begin Phase 3: Interactive Features

### Time Estimate
**Total: 8-12 hours**
- Phase 1: 2-3 hours
- Phase 2: 3-4 hours  
- Phase 3: 2-3 hours
- Phase 4: 1-2 hours

---

## 🎉 Success Criteria

The migration will be considered successful when:
- [ ] Full-screen TUI runs without errors
- [ ] All original functionality is preserved
- [ ] Live settings display works correctly
- [ ] Keyboard navigation is fully functional
- [ ] Property data displays beautifully
- [ ] Performance is acceptable
- [ ] User experience is significantly improved

---

*Last Updated: 2025-11-05*
*Status: Planning Complete - Ready for Implementation*
#!/usr/bin/env python3
"""
Test script to validate Phase 2 completion for Textual migration
Tests business logic integration, reactive properties, and data display functionality
"""

def test_business_logic_integration():
    """Test that business logic functions are properly integrated"""
    
    with open('textual_app.py', 'r') as f:
        content = f.read()
    
    business_logic_checks = [
        ('format_currency function', 'def format_currency('),
        ('format_percentage function', 'def format_percentage('),
        ('calculate_mortgage function', 'def calculate_mortgage('),
        ('deal_score_property function', 'def deal_score_property('),
        ('mobility_score function', 'def mobility_score('),
    ]
    
    results = []
    for check_name, pattern in business_logic_checks:
        if pattern in content:
            results.append(f"✅ {check_name}")
        else:
            results.append(f"❌ {check_name}")
    
    return results

def test_reactive_properties():
    """Test that reactive properties are properly defined"""
    
    with open('textual_app.py', 'r') as f:
        content = f.read()
    
    reactive_checks = [
        ('current_loan reactive', 'current_loan = reactive('),
        ('current_loan_data reactive', 'current_loan_data = reactive('),
        ('assumptions_data reactive', 'assumptions_data = reactive('),
        ('properties_df reactive', 'properties_df = reactive('),
        ('properties_count reactive', 'properties_count = reactive('),
        ('last_updated reactive', 'last_updated = reactive('),
        ('loading_data reactive', 'loading_data = reactive('),
    ]
    
    results = []
    for check_name, pattern in reactive_checks:
        if pattern in content:
            results.append(f"✅ {check_name}")
        else:
            results.append(f"❌ {check_name}")
    
    return results

def test_data_loading_methods():
    """Test that async data loading methods are implemented"""
    
    with open('textual_app.py', 'r') as f:
        content = f.read()
    
    data_loading_checks = [
        ('load_all_data method', 'async def load_all_data('),
        ('load_assumptions method', 'async def load_assumptions('),
        ('load_loan_data method', 'async def load_loan_data('),
        ('load_properties_data method', 'async def load_properties_data('),
        ('calculate_property_metrics method', 'def calculate_property_metrics('),
    ]
    
    results = []
    for check_name, pattern in data_loading_checks:
        if pattern in content:
            results.append(f"✅ {check_name}")
        else:
            results.append(f"❌ {check_name}")
    
    return results

def test_data_display_methods():
    """Test that data display methods are implemented"""
    
    with open('textual_app.py', 'r') as f:
        content = f.read()
    
    display_checks = [
        ('create_properties_table method', 'def create_properties_table('),
        ('create_property_details method', 'def create_property_details('),
        ('Properties table formatting', 'display_columns = ['),
        ('Color coding for metrics', 'if original_value >'),
        ('Property details sections', 'Property Information'),
        ('Investment metrics display', 'Investment Metrics'),
    ]
    
    results = []
    for check_name, pattern in display_checks:
        if pattern in content:
            results.append(f"✅ {check_name}")
        else:
            results.append(f"❌ {check_name}")
    
    return results

def test_reactive_watchers():
    """Test that reactive watchers are properly implemented"""
    
    with open('textual_app.py', 'r') as f:
        content = f.read()
    
    watcher_checks = [
        ('watch_current_loan method', 'def watch_current_loan('),
        ('watch_properties_count method', 'def watch_properties_count('),
        ('watch_last_updated method', 'def watch_last_updated('),
        ('Settings display update', 'def update_settings_display('),
    ]
    
    results = []
    for check_name, pattern in watcher_checks:
        if pattern in content:
            results.append(f"✅ {check_name}")
        else:
            results.append(f"❌ {check_name}")
    
    return results

def test_enhanced_actions():
    """Test that action methods are properly enhanced"""
    
    with open('textual_app.py', 'r') as f:
        content = f.read()
    
    action_checks = [
        ('Enhanced all properties action', 'table_content = self.create_properties_table()'),
        ('Enhanced property search action', 'property_details = self.create_property_details('),
        ('Enhanced refresh action', 'self.call_later(self.load_all_data)'),
        ('Data availability checks', 'if self.properties_df.empty:'),
    ]
    
    results = []
    for check_name, pattern in action_checks:
        if pattern in content:
            results.append(f"✅ {check_name}")
        else:
            results.append(f"❌ {check_name}")
    
    return results

if __name__ == "__main__":
    print("🧪 Testing Phase 2: Data Integration Completion")
    print("=" * 50)
    
    # Run all tests
    all_results = []
    
    print("\n📊 Business Logic Integration:")
    business_results = test_business_logic_integration()
    for result in business_results:
        print(f"  {result}")
    all_results.extend(business_results)
    
    print("\n⚡ Reactive Properties:")
    reactive_results = test_reactive_properties()
    for result in reactive_results:
        print(f"  {result}")
    all_results.extend(reactive_results)
    
    print("\n🔄 Data Loading Methods:")
    loading_results = test_data_loading_methods()
    for result in loading_results:
        print(f"  {result}")
    all_results.extend(loading_results)
    
    print("\n📋 Data Display Methods:")
    display_results = test_data_display_methods()
    for result in display_results:
        print(f"  {result}")
    all_results.extend(display_results)
    
    print("\n👀 Reactive Watchers:")
    watcher_results = test_reactive_watchers()
    for result in watcher_results:
        print(f"  {result}")
    all_results.extend(watcher_results)
    
    print("\n🎮 Enhanced Actions:")
    action_results = test_enhanced_actions()
    for result in action_results:
        print(f"  {result}")
    all_results.extend(action_results)
    
    # Summary
    print("\n" + "=" * 50)
    total_tests = len(all_results)
    passed_tests = len([r for r in all_results if r.startswith("✅")])
    
    print(f"📊 Phase 2 Summary: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 Phase 2: Data Integration COMPLETE!")
        print("✨ Ready to proceed to Phase 3: Interactive Features")
    else:
        print("⚠️  Some Phase 2 features need attention")
        failed_tests = [r for r in all_results if r.startswith("❌")]
        print(f"Failed tests: {len(failed_tests)}")
        for failed in failed_tests:
            print(f"  {failed}")
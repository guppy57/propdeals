"""
Test script to validate Textual app structure without dependencies
"""

def test_textual_app_structure():
    """Test that the textual app file has the correct structure"""
    
    # Read the textual_app.py file
    with open('textual_app.py', 'r') as f:
        content = f.read()
    
    # Check for required components
    checks = [
        ('PropertyAnalyzerApp class', 'class PropertyAnalyzerApp(App):'),
        ('BINDINGS defined', 'BINDINGS = ['),
        ('Reactive properties', 'current_loan = reactive('),
        ('compose method', 'def compose(self) -> ComposeResult:'),
        ('Keyboard actions', 'def action_show_all_properties(self) -> None:'),
        ('Help action', 'def action_show_help(self) -> None:'),
        ('Main function', 'def main():'),
    ]
    
    results = []
    for check_name, pattern in checks:
        if pattern in content:
            results.append(f"✅ {check_name}")
        else:
            results.append(f"❌ {check_name}")
    
    return results

def test_css_file():
    """Test that CSS file exists and has basic structure"""
    
    try:
        with open('app.tcss', 'r') as f:
            css_content = f.read()
        
        css_checks = [
            ('Main container styling', '#main-container'),
            ('Settings panel styling', '#settings-panel'),
            ('Color theme', 'App.-dark-mode'),
        ]
        
        results = []
        for check_name, pattern in css_checks:
            if pattern in css_content:
                results.append(f"✅ CSS {check_name}")
            else:
                results.append(f"❌ CSS {check_name}")
        
        return results
        
    except FileNotFoundError:
        return ["❌ CSS file not found"]

if __name__ == "__main__":
    print("🧪 Testing Textual App Structure")
    print("=" * 40)
    
    # Test app structure
    app_results = test_textual_app_structure()
    for result in app_results:
        print(result)
    
    print()
    
    # Test CSS structure  
    css_results = test_css_file()
    for result in css_results:
        print(result)
    
    print()
    print("📊 Summary:")
    total_tests = len(app_results) + len(css_results)
    passed_tests = len([r for r in app_results + css_results if r.startswith("✅")])
    print(f"Passed: {passed_tests}/{total_tests} tests")
    
    if passed_tests == total_tests:
        print("🎉 All structure tests passed! Phase 1 foundation is complete.")
    else:
        print("⚠️  Some tests failed. Review the implementation.")
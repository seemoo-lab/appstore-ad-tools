//
//  app_store_ad_extractionUITests.swift
//  app_store_ad_extractionUITests
//
//  Created by David Breuer on 26.03.24.
//

import XCTest
import Foundation
import Network
import os



final class ui_testUITests: XCTestCase {
    
    static var TIMEOUT_LENGTH = TimeInterval(180)
    static var APP_INSTALL_TIMOUT_LENGTH = TimeInterval(900)
    static var MAX_NETWORK_RETRIES = 99
    
    var monitor : NWPathMonitor!
    
    var api_token : String!
    var api_endpoint : String!
        
    struct AdDataRequest : Encodable {
        let id : Int
        let experiment_id : Int
        let time : String
        let label : String
        let sub_label : String
        let from_search_page : Bool
        let type : String
    }
    
    struct AccountReqquest : Encodable {
        let email : String
    }
    
    struct AccountResponse : Codable {
        let password : String
        let birth : String
        let city : String
        let postalcode : Int
        let persona_id : Int
        let gender : String
        let phonenumber : String
        let first_name : String
        let sur_name : String
        let email : String
        let country : String
        let street : String
        let street_number : Int
    }
    
    struct AppResponse : Codable {
        let id : Int
        let app_detail_id : Int?
        let apple_id : String?
        let google_id : String?
        let name : String
    }
    
    struct PersonaAppsRequest : Encodable {
        let id : Int //Persona Id
    }
    
    struct PersonaAppsResponse : Codable {
        let apps : [AppResponse]
    }
    
    struct AccountAppRequest : Encodable {
        let email : String
        let app_id : Int
        let time : String
    }
    
    override func setUpWithError() throws {
        continueAfterFailure = false
    }
    
    override func setUp() {
        //setup code
        self.continueAfterFailure = false
        
        let env = ProcessInfo.processInfo.environment
        api_token = env["API_TOKEN"]!
        api_endpoint = env["API_ENDPOINT"]!
        let skip_cellular_warning = env["SKIP_CELLULAR_WARNING"] == "1"
        
        //prevent screen from sleeping
        UIApplication.shared.isIdleTimerDisabled = true
        
        //monitor if we are connected via wifi all the time
        monitor = NWPathMonitor()
        
        monitor.pathUpdateHandler = { path in
            
            if path.status != .satisfied {
                NSLog("Lost Network connection...")
            }
            else {
                if path.isExpensive {
                    NSLog("Uses cellular data!")
                }
            }
            
            if path.availableInterfaces.contains(where: { interface in
                interface.type == NWInterface.InterfaceType.cellular
            }) {
                if !skip_cellular_warning {
                    NSLog("SEEMOO_connection_cellular")
                    XCTAssertTrue(false) //force xctest to terminate
                }
                
            }
        }
        
        let queue = DispatchQueue(label: "Monitor")
        monitor.start(queue: queue)
    }

    override func tearDownWithError() throws {
        // Put teardown code here. This method is called after the invocation of each test method in the class.
    }
    
    @MainActor
    func test_install_apps() async throws {
        await check_connection(app: nil)
        let env = ProcessInfo.processInfo.environment
        
        //parameters
        let account_email : String = env["ACCOUNT_EMAIL"]!
        let api_token : String = env["API_TOKEN"]!
        let url_account = URL(string: api_endpoint+"/account")!
        let url_persona_apps = URL(string: api_endpoint+"/persona/apps")!
    
        
        let account_data : AccountResponse? = await get_data_from_api(url: url_account, queryItems: [URLQueryItem(name: "email", value: account_email)])
        
        let persona_apps : [AppResponse]? = await get_data_from_api(url: url_persona_apps, queryItems: [URLQueryItem(name: "id", value: account_data!.persona_id.formatted())])
        
        print("Start install apps...")
        do {
            try await self.install_apps(persona_apps: persona_apps!, account_data: account_data!, api_token: api_token)
            
        } catch {
            print(error)
        }

    }
    
    
    @MainActor
    func probe_app(app: XCUIApplication, app_name: String, account_data : AccountResponse) -> Bool{
        //goto search page
        let search_button = app.buttons["AppStore.tabBar.search"]
        search_button.tap()
        handle_page_loading(app: app)
        
        //find search field
        let searchfield = app.searchFields.firstMatch
        searchfield.tap()
        
        //clear old search query
        if searchfield.buttons["Clear text"].exists {
            searchfield.buttons["Clear text"].tap()
        }
        
        //enter search query
        searchfield.typeText(app_name)
        
        app.buttons["search"].tap()
        handle_page_loading(app: app)
        
        _ = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH[c] %@", "AppStore.offerButton")).firstMatch.waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        //choose app by name
        
        return app.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] %@",app_name)).firstMatch.exists
    }
    
    @MainActor
    func install_apps(persona_apps : [AppResponse], account_data : AccountResponse, api_token : String) async throws {
        //go to home screen
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        
        //open app store
        let app = XCUIApplication(bundleIdentifier: "com.apple.AppStore")
        await check_connection(app: app)
        app.launch()
        sleep(10) //wait for 5 seconds
        check_and_solve_app_store_onboarding(app: app)
        check_and_solve_app_store_onboarding(app: app)
        
        for persona_app in persona_apps {
            await check_connection(app: app)
            var should_open = true
            while install_app(app: app, app_name: persona_app.name, account_data: account_data, should_open: &should_open) == false {
                NSLog("App %@ not installed. Retrying...", persona_app.name)
                if app.alerts.firstMatch.exists {
                    if app.alerts.firstMatch.buttons["OK"].exists {
                        app.alerts.firstMatch.buttons["OK"].tap()
                    }
                }
            }

            //log app install in database
            await self.post_data_to_api(url: URL(string:api_endpoint+"/account/app")!, payload: AccountAppRequest(email: account_data.email, app_id: persona_app.id, time: ISO8601DateFormatter().string(from:Date.now)))
            //wait for additional 5 seconds to be sure
            sleep(5)
            
            if should_open {
                //open app
                app.buttons["Open"].firstMatch.tap()
                sleep(10)
                
                app.activate()
            }
            
            sleep(3)
        }
        
        
        //exit App store
        app.terminate()
    }
    
@MainActor
    func install_app(app: XCUIApplication, app_name: String, account_data : AccountResponse, should_open : inout Bool) -> Bool{
        //goto search page
        let search_button = app.buttons["AppStore.tabBar.search"]
        search_button.tap()
        handle_page_loading(app: app)
        
        //find search field
        let searchfield = app.searchFields.firstMatch
        searchfield.tap()
        
        //clear old search query
        if searchfield.buttons["Clear text"].exists {
            searchfield.buttons["Clear text"].tap()
        }
        
        //enter search query
        searchfield.typeText(app_name)
        
        app.buttons["search"].tap()
        handle_page_loading(app: app)
        
        _ = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH[c] %@", "AppStore.offerButton")).firstMatch.waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        //choose app by name
        let app_button = app.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] %@",app_name)).firstMatch
        app_button.tap()
        
        //check if app is already bought or installed
        let offerButton = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH[c] %@", "AppStore.offerButton")).firstMatch
        
        _ = offerButton.waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        
        if offerButton.label == "Open" || offerButton.label == "Update" {
            //is already installed, do nothing...
            should_open = false
            return true
            
        } else if offerButton.label == "re-download" {
            //app is already bought
            offerButton.tap()
            sleep(3)
            if app.secureTextFields.firstMatch.exists {
                app.secureTextFields.firstMatch.typeText(account_data.password)
                app.buttons["Sign In"].tap()
            }
            
            sleep(3)
            skip_save_password_alert(app: app)
            sleep(2)
            skip_save_password_alert(app: app)
            
            let open_exists = app.buttons["Open"].waitForExistence(timeout: ui_testUITests.APP_INSTALL_TIMOUT_LENGTH)
            
            if open_exists {
                should_open = true
                return app.buttons["Open"].waitForHittable(timeout: ui_testUITests.APP_INSTALL_TIMOUT_LENGTH)
            }
            else {
                return false
            }
            
        } else {
            //app is not bought and not installed
            //install
            offerButton.tap()
            
            if check_for_first_login(app: app, account_data: account_data) {
                offerButton.tap()
            }
            sleep(3)
            //enter password & confirm
            app.secureTextFields.firstMatch.typeText(account_data.password)
            app.buttons["Sign In"].tap()
            
            sleep(7)
            
            if check_for_first_login(app: app, account_data: account_data) {
                offerButton.tap()
                
                sleep(5)
                
                //enter password & confirm
                app.secureTextFields.firstMatch.typeText(account_data.password)
                app.buttons["Sign In"].tap()
            }
            
            _ = XCUIApplication(bundleIdentifier: "com.apple.springboard").buttons["Install"].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
            XCUIApplication(bundleIdentifier: "com.apple.springboard").buttons["Install"].tap()
            
            //wait until springboard stops blocking the view...
            XCUIApplication(bundleIdentifier: "com.apple.springboard").buttons["Sign In"].waitForNotExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
            sleep(3)
            skip_save_password_alert(app: app)
            sleep(2)
            skip_save_password_alert(app: app)
            
            let open_exists = app.buttons["Open"].waitForExistence(timeout: ui_testUITests.APP_INSTALL_TIMOUT_LENGTH)
            
            if open_exists {
                should_open = true
                return app.buttons["Open"].waitForHittable(timeout: ui_testUITests.APP_INSTALL_TIMOUT_LENGTH)
            }
            else {
                return false
            }
        }
    }
    
    @MainActor
    func skip_save_password_alert(app : XCUIApplication) {
        
        if app.alerts.firstMatch.exists {
            if app.alerts.firstMatch.label.contains("Require password") {
                app.alerts.firstMatch.buttons["Always Require"].tap()
            }
            else if app.alerts.firstMatch.label.contains("Save password") {
                app.alerts.firstMatch.buttons["Not now"].tap()
            }
            
        }
    }
    
    func get_data_from_api<T : Decodable>(url : URL, queryItems : [URLQueryItem]) async -> T? {
        
        var url = url
        url.append(queryItems: queryItems)
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue(api_token, forHTTPHeaderField: "Authorization")
        
        for _ in 0 ..< ui_testUITests.MAX_NETWORK_RETRIES {
            do {
                let (data, _) =  try await URLSession.shared.data(for: request)
                let decoded = try JSONDecoder().decode(T.self, from: data)
                return decoded
            }
            catch {
                //pass and retry...
            }
            //wait for 2 seconds and retry...
            sleep(2)
        }
        return nil
    }
    
    func post_data_to_api<T : Encodable>(url : URL, payload : T) async {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.httpBody = try! JSONEncoder().encode(payload)
        request.setValue(
            "application/json",
            forHTTPHeaderField: "Content-Type"
        )
        
        request.setValue(
            api_token,
            forHTTPHeaderField: "Authorization"
        )
        for _ in 0 ..< ui_testUITests.MAX_NETWORK_RETRIES {
            do {
                let (_, response) = try await URLSession.shared.data(for: request)
                if (response as! HTTPURLResponse).statusCode == 200 {
                    break
                }
                
            }
            catch {
                //retry...
            }
            //wait for 2 seconds and retry...
            sleep(2)
        }
        
    }
    
    
    @MainActor
    func check_for_first_login(app : XCUIApplication, account_data : AccountResponse) -> Bool{
        if app.alerts.firstMatch.exists {
            let icloud_alert = app.alerts.firstMatch
            if icloud_alert.label.contains("Use the Apple") || icloud_alert.label.contains("This Apple Account has not yet been"){
                
                sleep(5)
                if icloud_alert.buttons["Sign In"].exists {
                    icloud_alert.buttons["Sign In"].tap()
                }
                
                
                sleep(3)
                
                _ = app.alerts.firstMatch.waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
                
                app.alerts.firstMatch.buttons["Review"].tap()
                
                sleep(5)
                _ = app.switches["Agree to Terms and Conditions"].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
                
                let condSwitch = app.switches["Agree to Terms and Conditions"]
                if condSwitch.value as? String == "0" {
                    condSwitch.tap()
                }
                app.buttons["Next"].tap()
                
                sleep(5)
                //fill in billing data
                let street_fields = app.textFields.matching(NSPredicate(format: "label BEGINSWITH[c] %@", "Street")).allElementsBoundByIndex
                for field in street_fields {
                    if field.placeholderValue! as String == "Required" {
                        field.tap()
                        field.typeText(account_data.street+" "+String(account_data.street_number))
                    }
                }
                let postcode_field = app.textFields["Postcode"]
                postcode_field.tap()
                postcode_field.typeText(String(account_data.postalcode))
                
                let city_field = app.textFields["City"]
                city_field.tap()
                city_field.typeText(account_data.city)
                
                let phone_field = app.textFields.matching(NSPredicate(format: "placeholderValue BEGINSWITH[c] %@", "123 ")).firstMatch
                phone_field.tap()
                phone_field.typeText(account_data.phonenumber)
                
                let next_buttons = app.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] %@", "Next")).allElementsBoundByIndex
                for b in next_buttons {
                    if b.isEnabled {
                        b.tap()
                        break
                    }
                }
                
                _ = app.buttons["Continue"].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
                
                app.buttons["Continue"].tap()
                
                return true
            }
        }
        
        return false
    }
    
    @MainActor
    func test_extract_ads() async throws {
        
        let env = ProcessInfo.processInfo.environment
        
        //Parameters...
        let exp_id : Int = Int(env["EXPERIMENT_ID"]!)!
        let url_data = URL(string: api_endpoint+"/ad_data")!
        let api_token : String = env["API_TOKEN"]!
        let first_ad_data_id : Int = Int(env["AD_DATA_ID"]!)!
        let minimum_ads : Int = Int(env["MINIMUM_AMOUNT_OF_ADS"]!)!
        
        var ad_id_counter = first_ad_data_id
        var extraction_counter = 0 //counts ads only
        
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        
        while extraction_counter < minimum_ads {
            
                    
            let app = XCUIApplication(bundleIdentifier: "com.apple.AppStore")
            await check_connection(app: app)
            app.launch()
            sleep(3)
            check_and_solve_app_store_onboarding(app: app)
            
            let today_button = app.buttons["Today"]
            //check if app store is loaded
            if today_button.exists && today_button.isHittable {
                today_button.tap()
            }
            else {
                continue
            }
            
            handle_page_loading(app: app)
            //wait until page is loaded
            _ = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH[c] %@", "AppStore.offerButton")).firstMatch.waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)

            var buttons = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@","Advertisement,")).allElementsBoundByIndex
            
            //extract from today page
            var current_time = Date()
            for button in buttons{
                let label = button.label.dropFirst("Advertisement, ".count).description

                
                NSLog("Ad output ad id: %i", ad_id_counter)
                NSLog("Ad output label: %@", label)
                
                await self.post_data_to_api(url: url_data, payload: AdDataRequest(id: ad_id_counter, experiment_id: exp_id, time: ISO8601DateFormatter().string(from: current_time), label: label, sub_label: "", from_search_page: false, type: "ad"))
                ad_id_counter += 1
                extraction_counter += 1 //counts ads only
            }
            
            //extract from search page
            app.buttons["Search"].tap()
            
            handle_page_loading(app: app)
            //wait until page is loaded
            _ = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH[c] %@", "AppStore.offerButton")).firstMatch.waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)

            buttons = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@","Advertisement,")).allElementsBoundByIndex
            

            current_time = Date()
            for button in buttons{
                let label = button.label.dropFirst("Advertisement, ".count).description
                let labelArray = label.components(separatedBy: ", ")
                var sublabel = ""
                if labelArray.count > 1 {
                    sublabel = labelArray[1]
                }

                
                NSLog("Ad output ad id: %i", ad_id_counter)
                NSLog("Ad output label: %@", label)
                
                await self.post_data_to_api(url: url_data, payload: AdDataRequest(id: ad_id_counter, experiment_id: exp_id, time: ISO8601DateFormatter().string(from: current_time), label: labelArray[0], sub_label: sublabel, from_search_page: true, type: "ad"))
                ad_id_counter += 1
                extraction_counter += 1 //counts ads only
            }
            
            //extract suggestions from search page
            var suggestions : [String] = []
            
            for cell in app.cells.allElementsBoundByIndex {
                if !suggestions.contains(cell.label) && cell.label != "" {
                    if !cell.label.contains("Advertisement") && cell.identifier.contains("AppStore.shelfItem.smallLockup"){
                        suggestions.append(cell.label)
                        
                    }
                    
                }
            }
            app.swipeUp()
            for cell in app.cells.allElementsBoundByIndex {
                if !suggestions.contains(cell.label) && cell.label != ""{
                    if !cell.label.contains("Advertisement") && cell.identifier.contains("AppStore.shelfItem.smallLockup"){
                        suggestions.append(cell.label)
                        
                    }
                }
            }
            app.swipeUp()
            for cell in app.cells.allElementsBoundByIndex {
                if !suggestions.contains(cell.label) && cell.label != ""{
                    if !cell.label.contains("Advertisement") && cell.identifier.contains("AppStore.shelfItem.smallLockup"){
                        suggestions.append(cell.label)
                        
                    }
                }
            }
            
            for item in suggestions {
                NSLog("Suggestion output label: %@", item)
                let labelArray = item.components(separatedBy: ", ")
                
                await self.post_data_to_api(url: url_data, payload: AdDataRequest(id: ad_id_counter, experiment_id: exp_id, time: ISO8601DateFormatter().string(from: current_time), label: labelArray[0], sub_label: labelArray[1], from_search_page: true, type: "suggestion"))
                ad_id_counter += 1
                
            }
            
            app.terminate()
       }
        
    }
    @MainActor
    func test_app_store_login() async throws {
        await check_connection(app: nil)
        let env = ProcessInfo.processInfo.environment
        
        let email = env["ACCOUNT_EMAIL"]!
        let password =  env["ACCOUNT_PASSWORD"]!
        
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        let app = XCUIApplication(bundleIdentifier: "com.apple.AppStore")
        app.launch()
        sleep(3)
        check_and_solve_app_store_onboarding(app: app)
        sleep(3)
        handle_page_loading(app: app)
        
        _ = app.buttons["AppStore.accountButton"].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        //TODO tap on account + login
        app.buttons["AppStore.accountButton"].tap()
        sleep(3)
        
        app.cells["AppStore.account.signIn"].tap()
        //Enter email
        let usernameField = app.textFields["username-field"]
        usernameField.tap()
        
        activate_keyboard(app: app)
        
        usernameField.typeText(email)
        app.keyboards.firstMatch.buttons["continue"].tap()
        
        //enter password
        _ = app.secureTextFields["password-field"].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        let passwordField = app.secureTextFields["password-field"]
        passwordField.tap()
        passwordField.typeText(password)
        app.keyboards.firstMatch.buttons["done"].tap()
        
        //wait for verification SMS
        sleep(20)
        
        
        
        //login finished
        
        //close app store
        app.terminate()
    }
    
    @MainActor
    func test_app_store_logout() async throws {
        await check_connection(app: nil)
        
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        
        app.staticTexts["Apple Account, iCloud+, and more"].tap()
        
        app.staticTexts["Sign Out"].tap()
        
        _ = app.tables.staticTexts["Sign in to access your iCloud data, the App Store, Apple Services, and more."].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        
        app.terminate()

    }
    
    @MainActor
    func test_is_logged_in() async throws {
        await check_connection(app: nil)
        let env = ProcessInfo.processInfo.environment
        
        let email = env["ACCOUNT_EMAIL"]!
        
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        sleep(2)
        
        let isLoggedin = app.staticTexts["Apple Account, iCloud+, and more"].exists
        
        if isLoggedin {
            app.staticTexts["Apple Account, iCloud+, and more"].tap()
            sleep(2)
            
            if !app.staticTexts[email.lowercased()].exists {
                XCTAssertTrue(false)
            }
        }
        else {
            XCTAssertTrue(false)
        }
        
        app.terminate()
    }
    
    
    
    @MainActor
    func test_login() async throws {
        await check_connection(app: nil)
        let env = ProcessInfo.processInfo.environment
        
        let email = env["ACCOUNT_EMAIL"]!
        let password =  env["ACCOUNT_PASSWORD"]!
        
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        
        //open login form
        let tablesQuery = app.tables
        tablesQuery/*@START_MENU_TOKEN@*/.staticTexts["Set up iCloud, the App Store, and more."]/*[[".cells[\"APPLE_ACCOUNT\"].staticTexts[\"Set up iCloud, the App Store, and more.\"]",".staticTexts[\"Set up iCloud, the App Store, and more.\"]"],[[[-1,1],[-1,0]]],[0]]@END_MENU_TOKEN@*/.tap()
        
        app.staticTexts["Sign in Manually"].tap()
        
        //enter username
        let usernameField = tablesQuery/*@START_MENU_TOKEN@*/.textFields["username-field"]/*[[".cells",".textFields[\"Email or Phone\"]",".textFields[\"username-field\"]"],[[[-1,2],[-1,1],[-1,0,1]],[[-1,2],[-1,1]]],[0]]@END_MENU_TOKEN@*/
        usernameField.tap()
        
        activate_keyboard(app: app)
        
        usernameField.typeText(email)
        app.keyboards.firstMatch.buttons["continue"].tap()
        
        //enter password
        _ = app.secureTextFields["Password"].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        let passwordField = app.secureTextFields["Password"]
        passwordField.tap()
        passwordField.typeText(password)
        app.keyboards.firstMatch.buttons["done"].tap()
        
        sleep(20)
       
        //check for terms and conditions
        if app.staticTexts["Terms and Conditions"].exists {
            app.buttons["Agree"].tap()
        }
        sleep(5)
        if app.alerts["Terms and Conditions"].exists {
            app.alerts["Terms and Conditions"].buttons["Agree"].tap()
        }
        sleep(10)
        //not use facetime:
        skip_face_time_alert()
        
        //skip additional icloud alerts...
        sleep(5)
        skip_face_time_alert()
        sleep(5)
        
        //skip alert
        skip_alert()
        
        app.terminate()
        
    }
 
    @MainActor
    func test_logout() async throws {
        await check_connection(app: nil)
        let env = ProcessInfo.processInfo.environment
        
        let password = env["ACCOUNT_PASSWORD"]!
        
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        
        app.staticTexts["Apple ID, iCloud, Media & Purchases"].tap()
        
        app.staticTexts["Sign Out"].tap()
        
        app.secureTextFields.firstMatch.typeText(password)

        app.buttons["Turn Off"].tap()
        
        _ = app.buttons["Sign Out"].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        app.buttons["Sign Out"].tap()
        
        app.alerts["Are you sure?"].buttons["Sign Out"].tap()
        
        //wait until finished
        _ = app.staticTexts["Set up iCloud, the App Store, and more."].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        
        app.terminate()

    }
    
    @MainActor
    func test_install_sim() async throws {
        await check_connection(app: nil)
        let env = ProcessInfo.processInfo.environment
        
        let smdpplusAddress = env["ADDRESS"]!
        let activationCode = env["ACTIVATION_CODE"]!
        let confirmationCode = env["CONFIRMATION_CODE"]! //ePIN
        
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        
        app.staticTexts["Cellular"].tap()
        
        app.staticTexts["Set Up Cellular"].tap()
        
        _ = app.staticTexts["Use QR Code"].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        app.staticTexts["Use QR Code"].tap()
        
        app.staticTexts["Enter Details Manually"].tap()
        
        activate_keyboard(app: app)
        
        app.textFields.allElementsBoundByIndex[0].typeText(smdpplusAddress)
        app.keyboards.firstMatch.buttons["next"].tap()
        
        app.textFields.allElementsBoundByIndex[1].typeText(activationCode)
        app.keyboards.firstMatch.buttons["next"].tap()
        
        app.textFields.allElementsBoundByIndex[2].typeText(confirmationCode)
        app.keyboards.firstMatch.buttons["continue"].tap()
        
        _ = app.staticTexts["Continue"].waitForExistence(timeout: ui_testUITests.TIMEOUT_LENGTH)
        app.staticTexts["Continue"].tap()
        
        _ = app.staticTexts["Done"].waitForExistence(timeout: TimeInterval(300)) //longer timeout
        app.staticTexts["Done"].tap()
        
        //deactivate cellular data
        let dataSwitch = app.switches["Cellular Data"]
        if dataSwitch.value as? String == "1" {
            dataSwitch.tap()
        }
        
        app.terminate()
        sleep(10)
        skip_alert()
        
        await check_connection(app: nil)
        
    }
    
    @MainActor
    func test_remove_current_sim() async throws {
        await check_connection(app: nil)
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        
        app.staticTexts["Cellular"].tap()
        
        app.staticTexts["Delete eSIM"].tap()
        
        app.buttons["Delete eSIM"].tap()//confirm deletion
        
        sleep(5)
        app.buttons["Delete eSIM"].tap()//confirm deletion again
        
        sleep(10)
        
        //skip alert
        skip_alert()
        
        app.terminate()
        
    }
    
    @MainActor
    func test_deactivate_cellular() throws {
        XCUIDevice.shared.press(XCUIDevice.Button.home)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        
        app.staticTexts["Cellular"].tap()
        
        let dataSwitch = app.switches["Cellular Data"]
        if dataSwitch.value as? String == "1" {
            dataSwitch.tap()
        }
        sleep(3)
        app.terminate()
    }
    
    @MainActor
    func test_privacy_settings_all_on() async throws {
        await check_connection(app: nil)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        
        app.staticTexts["Privacy & Security"].tap()
        
        app.staticTexts["LOCATION"].tap()
        
        set_switch(app: app, label: "Location Services", value: "1")
        
        //go back
        app.navigationBars.buttons.element(boundBy: 0).tap()
        
        //analytics settings
        app.staticTexts["PROBLEM_REPORTING"].tap()
        
        //activate everything
        set_switch(app: app, label: "Share iPhone Analytics", value: "1")
        for sw in app.switches.allElementsBoundByIndex {
            set_switch(app: app, label: sw.label , value: "1")
        }
        
        sleep(2)
        
        app.terminate()
        
    }
    
    @MainActor
    func test_deactivate_personalized_ads() async throws {
        await check_connection(app: nil)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        
        app.staticTexts["Privacy & Security"].tap()
        
        app.staticTexts["Apple Advertising"].tap()
        
        sleep(5)
        
        set_switch(app: app, label: "Personalized Ads", value: "0")
        
        sleep(2)
        
        app.terminate()
    }
    
    @MainActor
    func test_activate_personalized_ads() async throws {
        await check_connection(app: nil)
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        
        app.staticTexts["Privacy & Security"].tap()
        
        app.staticTexts["Apple Advertising"].tap()
        
        sleep(5)
        
        set_switch(app: app, label: "Personalized Ads", value: "1")
        
        sleep(2)
        
        app.terminate()
    }
    
    @MainActor
    func test_display_always_on() async throws {
        await check_connection(app: nil)
        await set_display_to_always_on(alwaysOn: true)
    }
    
    @MainActor
    func test_display_auto_off() async throws {
        await check_connection(app: nil)
        await set_display_to_always_on(alwaysOn: false)
    }
    
    @MainActor
    func set_display_to_always_on(alwaysOn : Bool) async {
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        sleep(1)
        
        app.staticTexts["DISPLAY"].tap()
        sleep(1)
        app.staticTexts["AUTOLOCK"].tap()
        
        if alwaysOn {
            app.staticTexts["Never"].tap()
        }
        else {
            app.staticTexts["30 seconds"].tap()
        }
        app.buttons["Display & Brightness"].tap()
        sleep(1)
        app.terminate()
    }
    
    @MainActor
    func set_switch(app :XCUIApplication, label : String, value : String) {
        if app.switches[label].value as? String != value {
            app.switches[label].tap()
        }
    }
    
    @MainActor
    func check_and_solve_app_store_onboarding(app : XCUIApplication) {
        sleep(3)
        if app.buttons["AppStore.onboarding.continueButton"].isHittable {
            app.buttons["AppStore.onboarding.continueButton"].tap()
            
            app.swipeUp()
            
            app.buttons["AppStore.onboarding.turnOnButton"].tap()
            sleep(3)
            handle_page_loading(app: app)
        }
        sleep(3)
        if app.staticTexts["Stay Up to Date with Notifications"].exists {
            app.staticTexts["Not Now"].tap()
        }
        sleep(3)
        if XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts["Allow “App Store” to use your approximate location?"].exists {
            XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts["Allow “App Store” to use your approximate location?"].firstMatch.buttons["Allow While Using App"].tap()
        }
        sleep(3)
        if app.staticTexts["Stay Up to Date with Notifications"].exists {
            app.staticTexts["Not Now"].tap()
        }
    }
    
    @MainActor
    func handle_page_loading(app: XCUIApplication) {
        while app.buttons["Retry"].isHittable {
            app.buttons["Retry"].tap()
            sleep(2)
        }
    }
    
    @MainActor
    func check_connection(app : XCUIApplication?) async {
        if monitor.currentPath.availableInterfaces.contains(where: { interface in
            interface.type == NWInterface.InterfaceType.cellular
        }) {
            NSLog("SEEMOO_connection_cellular")
            app?.terminate()
            XCTAssertTrue(false) //Force test to terminate
        }
        else {
            //check if our server is reachable
            
            var request_alive = URLRequest(url: URL(string: api_endpoint+"/alive")!, timeoutInterval: TimeInterval(3))
            request_alive.httpMethod = "GET"
            
            request_alive.setValue(
                api_token,
                forHTTPHeaderField: "Authorization"
            )
            for _ in 0 ..< ui_testUITests.MAX_NETWORK_RETRIES {
                do {
                    let (_, urlResponse) = try await URLSession.shared.data(for: request_alive)
                    if (urlResponse as! HTTPURLResponse).statusCode != 200 {
                        NSLog("SEEMOO_connection_bad")
                        app?.terminate()
                        XCTAssertTrue(false)
                    }
                    else {
                        break
                    }
                }
                catch {
                    //retry...
                }
            }
        }
    }
    
    @MainActor
    func skip_alert() {
        if XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.firstMatch.exists {
            XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.buttons["OK"].tap()
        }
    }
    
    @MainActor
    func skip_face_time_alert() {
        if XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts["Turn on FaceTime?"].exists {
            XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts["Turn on FaceTime?"].buttons["Don't Use"].tap()
        }
        
        if XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts["Turn on iMessage and FaceTime?"].exists {
            XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts["Turn on iMessage and FaceTime?"].buttons["Don't Use"].tap()
        }
        
        if XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts["Turn on iCloud?"].exists {
            XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts["Turn on iCloud?"].buttons["Don't Use"].tap()
        }
    }
    
    @MainActor
    func activate_keyboard(app : XCUIApplication) {
        //app.keyboards
        sleep(2)
        if !app.keyboards.buttons["shift"].isHittable {
            app.buttons["Continue"].firstMatch.tap()
        }
    }

}


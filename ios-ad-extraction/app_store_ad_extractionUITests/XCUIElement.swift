//
//  XCUIElement.swift
//  app_store_ad_extractionUITests
//
//  Created by David Breuer on 28.03.24.
//

import XCTest

extension XCUIElement {

    @discardableResult
    func waitForHittable(timeout: TimeInterval) -> Bool {
        let predicate   = NSPredicate(format: "exists == true && isHittable == true")
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: self)

        let result = XCTWaiter().wait(for: [ expectation ], timeout: timeout)

        return result == .completed
    }
    
    @discardableResult
    func waitForNotExistence(timeout: TimeInterval) -> Bool {
        let predicate   = NSPredicate(format: "isHittable == false")
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: self)

        let result = XCTWaiter().wait(for: [ expectation ], timeout: timeout)

        return result == .completed
    }
}

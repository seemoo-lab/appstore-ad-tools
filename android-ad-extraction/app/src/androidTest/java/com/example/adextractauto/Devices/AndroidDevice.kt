package com.example.adextractauto.Devices

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.wifi.WifiInfo
import android.util.Log
import android.view.KeyEvent.KEYCODE_ENTER
import android.view.Surface
import androidx.test.core.app.ApplicationProvider
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.Direction
import androidx.test.uiautomator.StaleObjectException
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.UiObjectNotFoundException
import androidx.test.uiautomator.UiScrollable
import androidx.test.uiautomator.UiSelector
import androidx.test.uiautomator.Until
import com.example.adextractauto.Account
import com.example.adextractauto.Ad
import com.example.adextractauto.App
import com.example.adextractauto.checkAlive
import com.example.adextractauto.fetchNextAdID
import com.example.adextractauto.getAccount
import com.example.adextractauto.getPersonaApps
import com.example.adextractauto.logAccountAction
import com.example.adextractauto.logAppInstall
import com.example.adextractauto.storeAdData
import org.hamcrest.CoreMatchers.notNullValue
import org.hamcrest.MatcherAssert.assertThat
import java.io.ByteArrayOutputStream
import java.time.Instant
import java.util.NoSuchElementException
import java.util.regex.Pattern

// global configuration values
const val MAX_RETRIES = 30
const val IDLE_TIMEOUT = 2000L // how long to wait for idle
const val SHORT_WAIT = 1000L // how long to wait for dialogues etc
const val LTAG = "AdExtractAuto"
private const val APP_STORE_IDENTIFIER = "com.android.vending"
const val SETTINGS_IDENTIFIER = "android.settings.SETTINGS"
private const val LAUNCH_TIMEOUT = 5_000L
private const val INSTALL_TIMEOUT = 900_000L
const val DEVICE_PIN = "0000"
const val WIFI_NETWORK = ""
const val WIFI_NETWORK_PASS = ""
const val ESIM_IDENTIFIER = ""

abstract class AndroidDevice(val device: UiDevice) {
    private var adId = 0  // incremented with each created ad
    private var appStoreOpenAttempts = 0
    // used to detect that we are trying to extract the same container as last iteration
    private var prevContainersAds: List<Ad>? = null

    // used for SMS code extraction
    enum class Platform {
        Apple, Google
    }

    /**
     * Wraps the given lambda into a while loop, catching NPEs and retrying up to MAX_RETRIES times.
     */
    fun performWithRetry(func: () -> Unit) {
        return performWithRetry(func, false, MAX_RETRIES)
    }

    /**
     * Wraps the given lambda into a while loop, catching NPEs and retrying up to MAX_RETRIES times.
     * If recoverable is true, does not log an error on failed perform.
     * This is useful if such cases are handled by the program.
     */
     fun performWithRetry(func: () -> Unit, recoverable: Boolean, maxRetries: Int) {
        for(i in 1..maxRetries) {
            try {
                func()
                device.waitForIdle(IDLE_TIMEOUT)
                return
            } catch(e: NullPointerException) {
                Log.i(LTAG, "Caught NPE, retrying - attempt $i/$maxRetries")
            }
            catch(e: StaleObjectException) {
                Log.i(LTAG, "Caught StaleObjectException, retrying - attempt $i/$maxRetries")
            }
            catch(e: UiObjectNotFoundException) {
                Log.i(LTAG, "Caught UIObjectNotFoundException, retrying - attempt $i/$maxRetries")
            }

            Thread.sleep(300L)
        }
        if(!recoverable) {
            // obtain current stack trace (the one from gradle is not too good)
            val stacktrace = try { throw IllegalStateException("getting_stacktrace") }
            catch(e: IllegalStateException) {e.stackTraceToString()}
            Log.e(LTAG, "Failed to run performWithRetry successfully: $stacktrace")
        }
        throw IllegalStateException("performWithRetry did not finish successfully.")
    }

    /**
     * Helper function, returns true if object is detected, else false.
     */
    fun detectObject(descriptor: BySelector) : Boolean {
        return detectObject(descriptor, IDLE_TIMEOUT)
    }

    fun detectObject(descriptor: BySelector, timeout: Long) : Boolean {
        val obj = device.wait(Until.hasObject(descriptor), timeout)
        return obj != null && obj != false
    }

    fun getSerial() : String {
        val serial = device.executeShellCommand("getprop ro.serialno").trim()
        if(serial.isBlank()) {
            Log.w(LTAG, "Tried to read serialno, but got empty result.")
        }
        return serial
    }

    open fun unlockDevice() {
        // sometimes, this fails, so retry a few times
        for(i in 0..3) {
            Log.i(LTAG, "Trying to unlock screen try $i.")

            // invoke unlock (two times to enter PIN entry)
            device.executeShellCommand("input keyevent 82")
            Thread.sleep(500L)
            // invoke unlock (two times to enter PIN entry)
            device.executeShellCommand("input keyevent 82")
            Thread.sleep(500L)

            // enter PIN
            device.executeShellCommand("input text 0000")
            Thread.sleep(500L)

            device.executeShellCommand("input keyevent 66")
            Thread.sleep(SHORT_WAIT)

            if(device.executeShellCommand("dumpsys deviceidle").contains("mScreenLocked=false\n")) {
                Log.i(LTAG, "Successfully unlocked screen.")
                return
            } else {
                Log.i(LTAG, "Failed to unlock screen, retrying...")
                device.executeShellCommand("input keyevent 82")
                Thread.sleep(SHORT_WAIT)
                // invoke unlock (two times to enter PIN entry)
                device.executeShellCommand("input keyevent 82")
                Thread.sleep(SHORT_WAIT)

                // try to get different possible states in iterations
                if(i % 2 == 0) {
                    device.executeShellCommand("input keyevent 82")
                    Thread.sleep(SHORT_WAIT)
                }
            }
        }
        assert(device.executeShellCommand("dumpsys deviceidle").contains("mScreenLocked=false\n"))
    }

    /**
     * Detects landscape mode and switches to portrait. Landscape mode sometimes messes up UI automation.
     * This should only be needed after opening apps that automatically switch to landscape (e.g., games).
     */
    fun fixScreenOrientation() {
        // check if in landscape mode
        if(device.displayRotation == Surface.ROTATION_90 || device.displayRotation == Surface.ROTATION_270) {
            Log.w(LTAG, "Found device in rotation ${device.displayRotation}, trying to switch to portrait mode.")
            device.setOrientationPortrait()
        }
    }

    /**
     * Function do dismiss payment popups. Returns true if it dismissed at least one popup.
     */
    private fun handlePaymentPopups() : Boolean {
        var performedInteraction = false
        for(i in 0..2) {
            // handle the "Complete account setup" dialogue that might appear
            if (detectObject(By.text("Complete account setup"), IDLE_TIMEOUT)) {
                // sometimes you have to click skip immediately
                if(detectObject(By.text("Skip"), IDLE_TIMEOUT)) {
                    performWithRetry { device.findObject(By.text("Skip")).click() }
                } else {
                    performWithRetry { device.findObject(By.text("Continue")).click() }
                    performWithRetry { device.findObject(By.text("Skip")).click() }
                }

                performedInteraction = true
                continue
            }

            // handle 'want to link your XYZ account'
            if (detectObject(By.textStartsWith("Want to link your "), IDLE_TIMEOUT)) {
                performWithRetry { device.findObject(By.text("No thanks")).click() }
                performedInteraction = true

                // after the paypal dialogue, this might appear, but you must not click continue
                if (detectObject(By.text("Complete account setup"), IDLE_TIMEOUT)) {
                    performWithRetry { device.findObject(By.text("Skip")).click() }
                    performedInteraction = true
                    continue
                }

                continue
            }

            // handle the "get google pass" popup
            if (detectObject(By.text("Not now"), IDLE_TIMEOUT)) {
                performWithRetry { device.findObject(By.text("Not now")).click() }
                performedInteraction = true
                continue
            }

            // handle the "rabatt" thing
            if(detectObject(By.textContains("No thanks"), SHORT_WAIT)) {
                performWithRetry { device.findObject(By.text("No thanks")).click() }
                performedInteraction = true
                continue
            }


            // found nothing actionable, exit
            return performedInteraction
        }
        return performedInteraction
    }

    private fun dismissAppStoreDialogues() {
        // handle all the dialogues that can come up.
        // order is unknown, so repeat multiple times(
        var iterations = 0
        while(true) {
            if(++iterations > 30) {
                throw IllegalStateException("Exceeded 30 iterations when trying to handle dialogues.")
            }

            // if the account accesses the playstore for the first time, we have to accept the terms and conditions
            if(detectObject(By.text("Terms of Service"), SHORT_WAIT)) {
                performWithRetry { device.findObject(By.text("Accept")).click() }
                continue
            }

            // additional search engines and browsers etc
            if(detectObject(By.textContains("You can choose additional"), SHORT_WAIT)) {
                // different confirm versions
                if(detectObject(By.textContains("No thanks"), SHORT_WAIT)) {
                    performWithRetry { device.findObject(By.text("No thanks")).click() }
                } else if(detectObject(By.textContains("Got it"), SHORT_WAIT)){
                    performWithRetry { device.findObject(By.text("Got it")).click() }
                } else if(detectObject(By.textContains("Next"), SHORT_WAIT)) {
                        performWithRetry { device.findObject(By.text("Next")).click() }
                } else if(detectObject(By.textContains("Finish"), SHORT_WAIT)) {
                    performWithRetry { device.findObject(By.text("Finish")).click() }
                }

                continue
            }

            // after additional engines, this reminder can popup
            if(detectObject(By.text("OK"), SHORT_WAIT)) {
                performWithRetry { device.findObject(By.text("OK")).click() }
                continue
            }

            // weird setup help thingy that pops up
            if(detectObject(By.textContains("Set up a new search"), SHORT_WAIT)) {
                if(detectObject(By.textContains("Got it"), SHORT_WAIT)) {
                    performWithRetry { device.findObject(By.text("Got it")).click() }
                    continue
                }
            }

            // handle the "Some Google services aren't linked" thing
            if(detectObject(By.text("Some Google services aren't linked"), SHORT_WAIT)) {
                // FIXME: Scroll to choose?

                performWithRetry { device.findObject(By.text("Get started")).click() }
                performWithRetry {
                    assert(UiScrollable(UiSelector().scrollable(true).className("androidx.recyclerview.widget.RecyclerView")).flingToEnd(100))
                }
                performWithRetry { device.findObject(By.text("Yes, link")).click() }
                continue
            }

            if(handlePaymentPopups()) continue

            // handle the "Google is optimizing" dialogue
            if(detectObject(By.textContains("Google is optimizing app"), SHORT_WAIT)) {
                performWithRetry { device.findObject(By.text("Got it")).click() }
                continue
            }

            // handle the "in the loop" dialogue
            if(detectObject(By.textContains("Want to stay in"), SHORT_WAIT)) {
                performWithRetry { device.findObject(By.text("No")).click() }
                continue
            }

            // weird "rabatt" offer
            if(detectObject(By.textContains("No thanks"), SHORT_WAIT)) {
                performWithRetry { device.findObject(By.text("No thanks")).click() }

                continue
            }


            // no dialogue was handled, so we exit
            break
        }
    }

    private fun dismissPopup() {
        // the popup blocks the search button, so we can use this to detect if it has been dismissed
        var iteration = 0

        dismissAppStoreDialogues()

        // on some devices, there is no search bar and the search button is in the bottom row
        while(device.findObject(By.text("Search apps & games")) == null
            && device.findObject(By.text("Search")) == null) {

            Log.i(LTAG, "Trying to dismiss the popup.")
            device.drag(260, 251, 203, 256, 200)

            // sometimes, there is this weird server busy screen -> maybe rate limiting?
            if(device.findObject(By.text("Server busy, please try again later.")) != null) {
                Log.w(LTAG, "Found 'Server Busy' message, sleeping and retrying.")
                Thread.sleep(60 * 1000)

                device.findObject(By.text("Try again"))?.click()
            }

            // try this again
            dismissAppStoreDialogues()

            // check if the PlayStore is open at all
            if(!detectObject(By.pkg(APP_STORE_IDENTIFIER).depth(0), SHORT_WAIT)) {
                Log.w(LTAG, "PlayStore seems to have closed, trying to re-open.")
                openAppstore()
            }

            if(iteration++ > 30) {
                Log.e(LTAG,"Failed to dismiss the popup, something went wrong.")
                throw IllegalStateException("Failed to dismiss the popup.")
            }
            device.waitForIdle(IDLE_TIMEOUT)
        }
    }

    private fun openAppstore() {
        // this should never happen, but to be safe.
        if(!device.isScreenOn) unlockDevice()

        device.pressHome()

        // clear the cache (+ user data)
        device.executeShellCommand("pm clear $APP_STORE_IDENTIFIER")

        // get launcher
        val launcherPackage: String = device.launcherPackageName
        assertThat(launcherPackage, notNullValue())

        // Launch the app
        val context = ApplicationProvider.getApplicationContext<Context>()
        val intent = context.packageManager.getLaunchIntentForPackage(
            APP_STORE_IDENTIFIER)?.apply {
            // Clear out any previous instances
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK)
        }
        context.startActivity(intent)

        // Wait for the app to appear
        if(!detectObject(By.pkg(APP_STORE_IDENTIFIER).depth(0), LAUNCH_TIMEOUT)) {
            // there might be this annoying popup, try pressing back
            device.pressBack()
            device.waitForIdle(IDLE_TIMEOUT)
            device.pressBack()
            device.waitForIdle(IDLE_TIMEOUT)
            device.pressBack()
            device.waitForIdle(IDLE_TIMEOUT)

            if(appStoreOpenAttempts++ > 30) {
                throw IllegalStateException("Exceeded 30 attempts to open the app store.")
            }

            return openAppstore()
        }
        // reset number of attempts
        appStoreOpenAttempts = 0

        // handle dialogues and popups
        dismissPopup()

        // make sure to select the "apps" tab. In some plastore versions, the playstore opens to the "games" tab
        performWithRetry {
            device.findObject(By.text("Apps")).click()
        }
    }

    private fun findAdContainer(): UiObject2? {
        // check if adContainer is visible
        var parentContainer = device.findObject(By.hasChild(By.text("Sponsored")))
        // relevant for initially visible ads
        var spons: UiObject2? = parentContainer?.findObject(By.text("Sponsored"))
        // detection of scroll end
        var lastHierarchy: String? = null

        var failedIterations = 0 // track to many failed iterations
        while (parentContainer == null || spons == null) {
            // scroll until sponsored is found (sometimes this fails and we cannot scroll)
            try {
                val scrollable = UiSelector().scrollable(true)
                UiScrollable(scrollable).scrollForward(200)
                Log.i(LTAG, "Tried to scroll forward.")
                failedIterations = 0
            } catch(e: UiObjectNotFoundException) {
                // for some unknown reason, the playstore simply closes sometimes
                // if this happens, just abort the data collection (we might miss out recommendations,
                // but if we freshly open the store we will get new data anyways)
                if(device.findObject(By.text("Top charts")) == null) {
                    Log.w(LTAG, "App store has disappeared, trying to re-open it.")
                    openAppstore()
                    continue
                }

                // else, try again
                assert(++failedIterations < 30)
                Thread.sleep(300L)
                continue
            }

            // try to detect end of scrolling by comparing hierarchies
            // this might fail if there is "auto scrolling" content at the end
            // if that happens, a timeout or something might be useful.
            val stream = ByteArrayOutputStream()
            device.dumpWindowHierarchy(stream)
            val currentHierarchy = stream.toString("UTF-8")
            if(lastHierarchy != null && lastHierarchy == currentHierarchy) {
                Log.i(LTAG, "Cannot scroll further, exiting.")
                return null
            } else {
                lastHierarchy = currentHierarchy
            }

            // there is this weird "Connectivity lost" / "Connection lost" thing that happened once.
            // No scrolling works, so the same container is extracted ad infinitum. Try to prevent this here.
            if(detectObject(By.text(Pattern.compile("conn?\\w* lost", Pattern.CASE_INSENSITIVE)),
                    timeout = SHORT_WAIT)) {
                Log.w(LTAG, "Detected connection loss issue, aborting this iteration.")
                return null
            }

            device.waitForIdle(IDLE_TIMEOUT)
            parentContainer = device.findObject(By.hasChild(By.text("Sponsored")))
            spons = parentContainer?.findObject(By.text("Sponsored"))
        }

        Log.i(LTAG, "found 'Sponsored' target, finished scrolling.")

        try {
            if (spons.visibleBounds.top > 1200) {
                Log.i(
                    LTAG,
                    "adContainer not fully visible (distance top: ${spons.visibleBounds.top}), trying to fix this by scrolling."
                )
                parentContainer.scroll(Direction.DOWN, 0.7f, 300)
            }

            // check where the ads begin in this container
            val idxSpons = parentContainer.children.indexOf(spons)

            // If this happens, something went wrong with the matching. recurse into this function to fix the issue
            if (idxSpons < 0) {
                return findAdContainer()
            }

            // adContainer contained at index idxSpons + 3
            return parentContainer.children[idxSpons + 3]
        } catch(e: StaleObjectException) {
            // something went wrong, just retry by recursing
            return findAdContainer()
        }
    }

    /**
     * Extracts all ads in a container and stores them by using the REST API.
     * Scrolls right as far as possible.
     */
    private fun extractAds(experimentId: Int, adContainer: UiObject2) : Boolean {
        // this list is maintained to recognize duplicated entries.
        val ads = mutableListOf<Ad>()
        @Suppress("NAME_SHADOWING")
        var adContainer = adContainer // mutable copy
        do {
            val time = Instant.now()

            try {
                val tmpAds = adContainer.children.mapNotNull {
                    if (it.childCount > 0) {
                        // handle new "rich" ads
                        if(try {// rich ads have only a star rating in the first child
                                it.children[0].children[0].contentDescription.startsWith("Star rating:")
                        } catch (e: IndexOutOfBoundsException) {false}) {
                            // if this is a rich add, the actual name is in the second child
                            val splitDesc = it.children[0].children[1].contentDescription.split("\n", limit=2)
                            return@mapNotNull Ad(adId++, experimentId, splitDesc[0], splitDesc[1], time.toString(), "ad")
                        }

                        // fix for weird single element adcontainers
                        it.children[0].contentDescription ?: return@mapNotNull null

                        // with some update mid of 2025, it is possible that child idx is 1 instead of 0

                        val adIdx = if(listOf("\nStar rating:", "\nEarly access", "\nComing soon", "\n").any { indicator -> it.children[0].contentDescription.contains(indicator) }) {
                            0
                        } else if(it.childCount > 1 && listOf("\nStar rating:", "\nEarly access", "\nComing soon", "\n").any { indicator -> it.children[1].contentDescription.contains(indicator) }) {
                            1
                        }
                        else {
                            Log.w(LTAG, "Non-ad entry found, ignoring.")
                            return@mapNotNull null
                        }

                        // "limit" specifies the number of elements in the list, not the splits performed
                        val splitDesc = it.children[adIdx].contentDescription.split("\n", limit=2)
                        Ad(adId++, experimentId, splitDesc[0], splitDesc[1], time.toString(), "ad")
                    } else null
                }

                // check if this is fully matches the previous container -> we probably failed to scroll
                // this should only be done the first time, therefore we are setting prevContainersAds to null in the else branch
                if(tmpAds.isNotEmpty() && (prevContainersAds ?: listOf()).containsAll(tmpAds)) {
                    // state of prevContainersAds should not matter here, because we will re-open the app store anyway
                    return false
                } else {
                    // if the first ads we encountered do not match the last ads in the previous container,
                    // this has to be a new container and we can set prevContainerAds to null.
                    prevContainersAds = null
                }

                // check if this is the end of ads by checking if there are new ones this iteration
                if(ads.containsAll(tmpAds)) {
                    // since we exit this iteration, we have to update the prevContainerAds
                    prevContainersAds = tmpAds
                    return true
                }

                /* There is some overlap, so previous ads are returned.
                 * it seems like in a single container, there are no duplicates anyways, so we just
                 * check it manually (and can't use addAll).
                 * Algorithmic complexity of this approach is pretty bad.
                 * But mutableSet did not really work, because contains() returned false.
                 */
                for (ad in tmpAds) {
                    if(!ads.contains(ad)) {
                        ads.add(ad)
                        storeAdData(ad)
                    }
                }

                adContainer.scroll(Direction.RIGHT, 1f)
            } catch (e: StaleObjectException) {
                // Sometimes objects get stale -> fix this by just calling findAdContainer again
                // findAdContainer can fail and return null, in this case we just continue with the next container
                // we don't want to abort the whole process, therefore return true
                adContainer = findAdContainer() ?: return true
                Log.i(LTAG, "adContainer got stale, recreating.")
            }
        } while(true)
    }

    private fun retrieveAllAds(experimentId: Int, device: UiDevice) {
        var adContainer = findAdContainer()
        while(adContainer != null) {
            // this can take some time and is important, so we check regularly if the server is alive
            checkAlive()

            // extract all ads. if extractAds returns false, stop this iteration.
            if(!extractAds(experimentId, adContainer)) {
                Log.i(LTAG, "Stopping AdExtraction iteration due to 'extractAds' returning false.")
                break
            }

            // scroll over current adContainer to search for the next one
            Log.i(LTAG, "Finished adExtraction, scrolling.")
            try {
                // scroll down. we cannot abort here, because this often returns false even though the container can scroll further.
                adContainer.parent.scroll(Direction.DOWN, 1f, 300)
            } catch (e: StaleObjectException) {
                // adContainer might go stale, re-fetch it
                findAdContainer()!!.parent.scroll(Direction.DOWN, 1f, 300)
            }

            device.waitForIdle(IDLE_TIMEOUT)
            // get the new adContainer
            adContainer = findAdContainer()
        }
        Log.i(LTAG, "Finished retrieving all ads.")
    }

    /**
     * Function to extract recommendations.
     * Should be called from `adExtractExperiment`, after extracting ads and while appstore is still open.
     */
    private fun extractRecommendations(experimentId: Int, device: UiDevice) {
        Log.i(LTAG, "Start to extract recommendations.")

        // scroll back up to search for the "Recommended for you" container
        var iteration = 0
        while(true) {
            // check also before hand (just to be sure)
            if(device.findObject(By.text("Recommended for you")) != null) {
                break
            }
            // for some reason, scroll to beginning will only give us half a screen
            performWithRetry {  UiScrollable(UiSelector().scrollable(true).instance(0)).scrollToBeginning(1000) }

            // try if there is the recommended section
            try {
                if(device.findObject(By.text("Recommended for you")) != null) {
                    performWithRetry(
                        {
                            device.findObject(By.text("Recommended for you")).click()

                            // make sure that the view is there
                            // use implicit retry mechanic to try to click again
                            detectObject(By.clazz("android.support.v7.widget.RecyclerView"))
                                    || throw java.lang.NullPointerException()
                        },
                        true,
                        MAX_RETRIES
                    )
                    break
                }
            } catch (e: IllegalStateException) {
                Log.i(LTAG, "Failed to click recommendation button, even though it has been detected. Continuing with scrolling.")
            }

            // we don't want to scroll ad infinitum
            if(iteration++ > 70) {
                Log.e(LTAG, "Failed to find recommendation container after 70 tries. Returning. ")
                return
            } else {
                Log.i(LTAG, "Trying to find recommendations in $iteration / 70.")
            }
        }

        // extract displayed apps
        val recommendations = mutableListOf<Ad>()
        iteration = 0 // reset iterations for this loop
        while (true) {
            try {
                val apps =
                    device.findObject(By.clazz("android.support.v7.widget.RecyclerView")).children.mapNotNull {
                        // limit works very weird and specifies the number of elements in the list, not the splits performed
                        val splitDesc =
                            it.contentDescription?.split("\n", limit = 2) ?: return@mapNotNull null
                        Ad(
                            adId++, experimentId, splitDesc[0].replace("App: ", ""),
                            splitDesc[1], Instant.now().toString(), "suggestion"
                        )
                    }

                for (app in apps) {
                    if (!recommendations.contains(app)) {
                        recommendations.add(app)
                        storeAdData(app)
                    }
                }

                try {
                    if (!UiScrollable(UiSelector().scrollable(true).instance(0)).scrollForward(80)) {
                        break
                    }
                } catch(e: UiObjectNotFoundException) {
                    Log.w(LTAG, "Caught UIObjectNotFoundException while scrolling, this should indicate the end of the list. Finishing recommendation extraction. ")
                    break
                }
            } catch(e: NullPointerException) {
                iteration++
                Log.w(LTAG, "Caught NPE while extracting recommendations, retrying loop (iteration=$iteration)")
                if(iteration > 30) {
                    Log.w(LTAG, "Aborting recommendation instructions, more than 30 NPEs in a row.")
                    break
                }
                continue
            }
        }
        Log.i(LTAG, "Finished retrieving all recommendations.")
    }

    private fun installAppInContainer(appContainer: UiObject2?, openApp: Boolean) {
        // click on the app container to open app description
        appContainer?.click()
        device.waitForIdle(IDLE_TIMEOUT)

        // if previous installation failed (due to process crash), the app might already be installed
        // we do not want to open it again.
        if(detectObject(By.text("Uninstall"))) {
            Log.w(LTAG, "App already installed, skipping.")
            device.pressBack()
            return
        }

        // click install button
        performWithRetry { device.findObject(By.text("Install")).click() }

        handlePaymentPopups()

        var iteration = 0
        // wait for open button to appear (for games, open is called "Play" instead)
        // originally, we also waited for uninstall, but UI changes produce apps that do not have that any longer.
        while((device.findObject(By.text("Open")) == null &&
               device.findObject(By.text("Play")) == null) ||
            device.findObject(By.text("Uninstall")) == null
        ) {
            Log.i(LTAG, "Waiting for installation to finish, iteration $iteration.")
            iteration++

            if(!device.isScreenOn) {
                Log.i(LTAG, "Screen was off, re-opening.")
                unlockDevice()
            }

            // these can appear here too
            handlePaymentPopups()

            // time for minimum sleeps in handlePaymentPopups
            if(INSTALL_TIMEOUT < iteration * 2 * IDLE_TIMEOUT) {
                throw IllegalStateException("Exceeded 15 minute of install timeout.")
            }
        }

        // open the app to signal a stronger intent
        if(openApp) {
            iteration = 0
            while(true) {
                if(detectObject(By.text("Open"))) {
                    Log.i(LTAG, "Found Open button, trying to open the app.")
                    performWithRetry { device.findObject(By.text("Open")).click() }
                } else if(detectObject(By.text("Play"))) {
                    Log.i(LTAG, "Found Play button, trying to open the app.")
                    performWithRetry { device.findObject(By.text("Play")).click() }
                } else {
                    Log.w(LTAG, "Found neither Open nor Play button, app perhaps already open.")
                    break
                }

                // check if playstore is still in the foreground (so we failed to open app)
                if(detectObject(By.pkg(APP_STORE_IDENTIFIER).depth(0), SHORT_WAIT)) {
                    Log.w(LTAG, "PlayStore is still there, retrying.")
                } else {
                    break
                }

                if(iteration++ > 10) {
                    Log.w(LTAG, "Failed to open the app, continuing.")
                    break
                }
            }
            Thread.sleep(10000L)
        } else {
            // if app was not opened, pressing back is enough
            device.pressBack()
        }
    }

    private fun getInstalledApps() : Set<String> {
        return device.executeShellCommand("pm list packages").split("\n").map {
            it.removePrefix("package:")
        }.toHashSet()
    }

    private fun getAppContainer(app: App) : UiObject2? {
        // we want to try an exact match first (to prevent something like 'Appname (Pro)' from being selected)
        val appContainerSelector = if(detectObject(By.descStartsWith(app.name+ "\n"))) {
            // selector for app container
            Log.i(LTAG, "Found app container using full match.")
            By.descStartsWith(app.name + "\n")
        } else {
            Log.i(LTAG, "Found app container using partial match only!")
            By.descStartsWith(app.name)
        }

        // wait until install button appears (this is not immediately for some reason)
        var appContainers = device.findObjects(appContainerSelector)

        var iteration = 0
        while(appContainers.isEmpty()) {
            appContainers = device.findObjects(appContainerSelector)
            if(appContainers.isNotEmpty()) break

            Thread.sleep(300L)
            Log.i(LTAG, "Sleeping while waiting for app container $iteration.")

            // sometimes, it is necessary to scroll first (if there are a lot of sponsored results)
            if(iteration > 10) {
                Log.i(LTAG, "Trying to scroll app name into view.")

                val scrollable = UiScrollable(
                    UiSelector()
                        .scrollable(true)
                )

                // scroll text into view does not work here for unknown reason
                scrollable.scrollForward(200)
            }

            if(++iteration > 30) {
                throw IllegalStateException("Exceeded 30 iterations when waiting for install app container.")
            }
        }

        // if there are multiple candidate, pick the one without star rating.
        // Reason for this is that the first match will be the ad, so we don't want to click that
        val container = if(appContainers.size > 1)
        // sometimes, this does not work and we need to pick simply the second one
            try {
                appContainers.first { !it.contentDescription.contains("Star rating: ") }
            } catch(e: NoSuchElementException) {
                appContainers.last()
            }
        else appContainers.first()

        // check if this app is already installed
        // clicking on apps to detect this does not work sometimes, will open the app instead
        if(container.contentDescription.contains("\nInstalled\n")) {
            return null
        }

        return container
    }

    private fun installApp(email: String, app: App, openApp: Boolean) {
        Log.i(LTAG, "Attempting app install for ${app.name}.")

        // fetch currently installed apps to see what we installed, in case it does not match our expectations
        val previouslyInstalled = getInstalledApps()

        // search sometimes fails, in that case try again
        var searchFailedCount = 0
        while(true) {
            try {
                // on some devices it is necessary to first switch to the search tab
                if(detectObject(By.text("Search"))) {
                    performWithRetry { device.findObject(By.text("Search")).click() }
                }

                // click search button
                device.findObject(By.text("Search apps & games")).click()
                Thread.sleep(SHORT_WAIT)

                // enter app name (longClickable is important to not select the wrong object)
                device.findObject(By.clazz("android.widget.EditText")).text = app.name
                Thread.sleep(SHORT_WAIT)

                // perform search
                device.pressKeyCode(KEYCODE_ENTER)
                Thread.sleep(SHORT_WAIT)
            } catch(e: NullPointerException) {
                Log.i(LTAG, "Caught NPE while trying to perform search, retrying.")
                continue
            }

            // exit only if we managed to perform the search
            if(device.findObject(By.text("Search apps & games")) == null) {
                break
            } else {
                Log.i(LTAG, "Failed to perform search ($searchFailedCount/30), retrying.")

                // re-open appstore
                if(searchFailedCount++ > 30){
                    Log.i(LTAG, "Reached 30 failed search attempts, re-opening appstore.")

                    device.pressBack()
                    device.waitForIdle(IDLE_TIMEOUT)
                    device.pressBack()
                    device.waitForIdle(IDLE_TIMEOUT)
                    device.pressBack()
                    device.waitForIdle(IDLE_TIMEOUT)

                    openAppstore()

                    searchFailedCount = 0
                }
            }
        }

        val appContainer = getAppContainer(app)
        if(appContainer == null) {
            Log.w(LTAG, "The app with bundle id ${app.googleId} is already installed.")
            device.pressBack()
            device.waitForIdle(IDLE_TIMEOUT)
            return
        }

        // perform the installation
        installAppInContainer(appContainer, openApp)

        device.waitForIdle(IDLE_TIMEOUT)

        // sanity check with the bundle id
        val installed = getInstalledApps()
        if(!installed.contains(app.googleId)) {
            val diff = installed - previouslyInstalled
            Log.w(LTAG, "Found unexpected bundle id: expected ${app.googleId} but found $diff.")
        }

        logAppInstall(email, app)

        if(openApp) {
            // restore app-store state
            openAppstore()
        } else {
            // press back button to return to store main page
            device.pressBack()
        }

        device.waitForIdle(IDLE_TIMEOUT)
    }

    open fun checkWIFIConnectivity() {
        val context = InstrumentationRegistry.getInstrumentation().context
        val connectivityManager = context.getSystemService(ConnectivityManager::class.java) as ConnectivityManager
        val winfo = connectivityManager.getNetworkCapabilities(connectivityManager.activeNetwork)?.transportInfo

        if(winfo == null) {
            Log.e(LTAG,"Expected to be connected to WIFI, but winfo was null.")
            throw IllegalStateException("Device is not connected to any WIFI/VPN, winfo is null.")
        }

        when(winfo.javaClass.name) {
            "android.net.wifi.WifiInfo" -> {
                if((winfo as WifiInfo).supplicantState.toString() != "COMPLETED") {
                    Log.e(LTAG,"Expected to be connected to WIFI.")
                    throw IllegalStateException("Device is not connected to any WIFI.")
                }
            }
            "android.net.VpnTransportInfo" -> {
                // if there is a VPN, it should be fine?
                // This should only happen for account creation on the dedicated device,
                // so we don't care about it for the main experiment.
                Log.i(LTAG,"Device connected to VPN, checkWIFIConnectivity is true.")
            }

            else -> {
                Log.e(LTAG,"Expected to be connected to WIFI / VPN, found unknown state: ${winfo.javaClass.name}.")
                throw IllegalStateException("Device is not connected to any WIFI.")
            }
        }
    }

    /*
     * Full "task" functions ------------------------------------------------------------------
     */
    fun disablePersonalization() {
        Log.i(LTAG, "Starting to disable Personalization.")

        // initial test that the harvester server is reachable
        checkAlive()

        // do this first to ensure that the screen is on before doing anything else
        if(!device.isScreenOn) unlockDevice()

        // open google settings
        openGoogleSettings()

        // different uis possible depending on the device / whether google services have been updated
        if(detectObject(By.textContains("Manage your Google Account"))) {
            // open the settings
            performWithRetry {
                device.findObject(By.textContains("Manage your Google Account")).click()
            }
        } else {
            // two clicks to navigate to this dialogue
            performWithRetry {
                device.findObject(By.textContains("gmail.com")).click()
            }
            performWithRetry {
                // can apparently either be "Google Account" or "Manage your Google Account"
                device.findObject(By.textContains("Google Account")).click()
            }
        }

        // go to privacy tab (if there is none, switch to "new" ui layout instead!!)
        if(!try {
                performWithRetry( { device.findObject(By.text("Data & privacy")).click()}, recoverable = true, maxRetries = 30)
                true
            }
            catch(e: IllegalStateException){ false }) {
            // new ui, different actions to get there
            performWithRetry {
                val scrollable = UiScrollable(UiSelector().className("android.support.v7.widget.RecyclerView"))
                scrollable.flingForward() // apparently, the scroll text into view does not hit this otherwise
                if(!detectObject(By.text("Data & privacy"))) scrollable.scrollTextIntoView("Data & privacy") || throw java.lang.NullPointerException()
            }
            // open data privacy dialogue
            performWithRetry {
                device.findObject(By.text("Data & privacy")).click()
            }
        }

        // some cursed accounts are not allowed to get ads. try to catch this here
        try {
            performWithRetry({
                val scrollable =
                    UiScrollable(UiSelector().className("android.support.v7.widget.RecyclerView"))
                scrollable.scrollTextIntoView("Ad personalization isn’t available for this account") || throw java.lang.NullPointerException()
            }, recoverable = true, 3)

            // if we are here, this account does not get personalized ads
            throw IllegalArgumentException("ACCOUNT_DOES_NOT_HAVE_PERSONALIZATION")

        } catch(e: IllegalStateException) {
            // this is good, we don't want to find that text
        }

        // find "My Ad Center" button by using implicit retries
        // for some reason, scrollTextIntoView fails sometimes
        performWithRetry {
            val scrollable = UiScrollable(UiSelector().className("android.support.v7.widget.RecyclerView"))
            scrollable.scrollTextIntoView("My Ad Center") || throw java.lang.NullPointerException()
        }

        // open ad center
        performWithRetry {
            device.findObject(By.text("My Ad Center")).click()
        }

        // check if already off. if so, abort
        if(detectObject(By.textContains("To get started, turn on personalized ads"))) {
            Log.w(LTAG, "Personalization is already off, continuing.")
            return
        }

        if(detectObject(By.text("Turn off"))) {
            // hit invisible turn off button
            performWithRetry { device.findObject(By.text("Turn off")).click()  }
        } else if (detectObject(By.desc("Turn off"))) {
            performWithRetry { device.findObject(By.desc("Turn off")).click()  }
        } else {
            throw IllegalStateException("Expected Turn off button not found!!")
        }

        // make sure we are in the intended dialogue
        detectObject(By.text("Turn off personalized ads?"))
                || throw IllegalStateException("Did not find expected text, either entered the wrong dialogue or personalization is already disabled.")

        // turn off (button click is not always registered for some reason, retry
        var iterations = 0
        do {
            performWithRetry {
                val list = device.findObjects(By.text("Turn off"))
                if(list.isNotEmpty()) {
                    list.last().click()
                }
            }
            Log.i(LTAG, "Finished performWithRetry, continuing in loop.")
            if (iterations++ > 30) throw IllegalStateException("Reached 30 iterations trying to click turn off button.")
        } while(detectObject(By.text("Turn off")))

        // make sure we were successful
        detectObject(By.text("Personalized ads are now off"))
                || throw IllegalStateException("Did not find expected confirmation text.")

        // acknowledge
        performWithRetry {
            device.findObject(By.text("Got it")).click()
        }

        detectObject(By.text("Personalized ads are off"))
                || throw IllegalStateException("Did not find expected second confirmation text.")

        // log this action to the database
        logAccountAction("PREV_ACC", getSerial(), "disablePersonalization")
    }

    fun enablePersonalization() {
        Log.i(LTAG, "Starting to enable Personalization.")

        // initial test that the harvester server is reachable
        checkAlive()

        // do this first to ensure that the screen is on before doing anything else
        if(!device.isScreenOn) unlockDevice()

        // open google settings
        openGoogleSettings()

        // different uis possible depending on the device / whether google services have been updated
        if(detectObject(By.textContains("Manage your Google Account"))) {
            // open the settings
            performWithRetry {
                device.findObject(By.textContains("Manage your Google Account")).click()
            }
        } else {
            // two clicks to navigate to this dialogue
            performWithRetry {
                device.findObject(By.textContains("gmail.com")).click()
            }
            performWithRetry {
                // can apparently either be "Google Account" or "Manage your Google Account"
                device.findObject(By.textContains("Google Account")).click()
            }
        }

        // go to privacy tab (if there is none, switch to "new" ui layout instead!!)
        if(!try {
                performWithRetry( { device.findObject(By.text("Data & privacy")).click()}, recoverable = true, maxRetries = 30)
                true
            }
            catch(e: IllegalStateException){ false }) {
            // new ui, different actions to get there
            performWithRetry {
                val scrollable = UiScrollable(UiSelector().className("android.support.v7.widget.RecyclerView"))
                scrollable.flingForward() // apparently, the scroll text into view does not hit this otherwise
                if(!detectObject(By.text("Data & privacy"))) scrollable.scrollTextIntoView("Data & privacy") || throw java.lang.NullPointerException()
            }
            // open ad center
            performWithRetry {
                device.findObject(By.text("Data & privacy")).click()
            }
        }

        // some cursed accounts are not allowed to get ads. try to catch this here
        try {
            performWithRetry({
                val scrollable =
                    UiScrollable(UiSelector().className("android.support.v7.widget.RecyclerView"))
                scrollable.scrollTextIntoView("Ad personalization isn’t available for this account") || throw java.lang.NullPointerException()
            }, recoverable = true, 3)

            // if we are here, this account does not get personalized ads
            throw IllegalArgumentException("ACCOUNT_DOES_NOT_HAVE_PERSONALIZATION")

        } catch(e: IllegalStateException) {
            // this is good, we don't want to find that text
        }

        // find "My Ad Center" button by using implicit retries
        // for some reason, scrollTextIntoView fails sometimes
        performWithRetry {
            val scrollable = UiScrollable(UiSelector().className("android.support.v7.widget.RecyclerView"))
            scrollable.scrollTextIntoView("My Ad Center") || throw java.lang.NullPointerException()
        }

        // open ad center
        performWithRetry {
            device.findObject(By.text("My Ad Center")).click()
        }

        // check that really off. if not, abort
        if(!detectObject(By.textContains("To get started, turn on personalized ads"))) {
            Log.w(LTAG, "Personalization is already on, continuing.")
            return
        }

        // hit invisible turn on button
        performWithRetry {
            device.findObject(By.text("Turn on")).click()
        }

        // make sure we are in the intended dialogue
        detectObject(By.text("Turn on personalized ads?"))
                || throw IllegalStateException("Did not find expected text, either entered the wrong dialogue or personalization is already disabled.")

        // turn off (button click is not always registered for some reason, retry
        var iterations = 0
        do {
            performWithRetry {
                val list = device.findObjects(By.text("Turn on"))
                if(list.isNotEmpty()) {
                    list.last().click()
                }
            }
            Log.i(LTAG, "Finished performWithRetry, continuing in loop.")
            if (iterations++ > 30) throw IllegalStateException("Reached 30 iterations trying to click turn off button.")
        } while(detectObject(By.text("Turn on")))

        // make sure we were successful
        detectObject(By.text("Personalized ads are now on"))
                || throw IllegalStateException("Did not find expected confirmation text.")

        // acknowledge
        performWithRetry {
            device.findObject(By.text("Got it")).click()
        }

        detectObject(By.textContains("Simply turn off"))
                || throw IllegalStateException("Did not find expected second confirmation text.")




        // log this action to the database
        logAccountAction("PREV_ACC", getSerial(), "enablePersonalization")
    }


    fun adExtractExperiment(experimentId: Int) {
        // do this first to ensure that the screen is on before creating an experiment
        if(!device.isScreenOn) unlockDevice()
        openAppstore()

        adId = fetchNextAdID(experimentId)
        Log.i(LTAG, "Starting measuring with next AddID=$adId as part of experiment with ID=$experimentId.")

        retrieveAllAds(experimentId, device)
        extractRecommendations(experimentId, device)

        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    fun signalPersona(email: String, openApps: Boolean) {
        Log.i(LTAG, "Starting to signal persona for $email, openApps=$openApps.")

        // initial test that the harvester server is reachable
        checkAlive()

        // do this first to ensure that the screen is on before doing anything else
        if(!device.isScreenOn) unlockDevice()
        openAppstore()

        // get the apps to be installed for this persona
        val apps = getPersonaApps(email)
        Log.i(LTAG, apps.toString())

        for(app in apps) {
            // try installation multiple times
            for(i in 0..10) {
                try {
                    installApp(email, app, openApps)
                    break
                } catch(e: IllegalStateException) {
                    Log.i(LTAG, "Retrying app installation due to '${e.message}'.")
                    for(u in 0..3) {
                        device.pressBack()
                        device.waitForIdle(IDLE_TIMEOUT)
                    }
                    openAppstore()
                }
                if(i >= 10) {
                    throw IllegalStateException("Exceeded 10 tries to install app ${app.name}")
                }
            }
        }
    }

    private fun handleAccountDialogues(account: Account) {
        // here a number of things can happen, handle these in a loop and continue until no action happened anymore
        var iteration = 0
        while(true) {
            Log.i(LTAG, "Iteration=${iteration++}, trying to handle optional Google interactions.")

            // generic skip
            if(detectObject(By.text("Skip"), IDLE_TIMEOUT * 2)) {
                performWithRetry { device.findObject(By.text("Skip")).click() }
            }

            // Here, it can happen that Google asks to use the number in the profile,
            // instead of showing terms of service -> we catch this and politely decline
            // this seems to be when there is a SIM when logging in -> we want to support both cases
            if(detectObject(By.textContains("Add phone number?"), IDLE_TIMEOUT * 2)) {
                // scroll until google text
                val ret = UiScrollable(UiSelector()
                    .scrollable(true))
                    .scrollTextIntoView("Skip")
                if(!ret) {
                    Log.e(LTAG, "Could not find decline button. Aborting.")
                    throw IllegalStateException("Failed to find decline button text.")
                }

                performWithRetry { device.findObject(By.text("Skip")).click() }

                // we did something, so re-enter loop
                continue
            }

            // Here it can also happen that Google is asking to verify phone number as second factor
            if(detectObject(By.text("Verify your phone number"), IDLE_TIMEOUT * 2)) {
                performWithRetry { device.findObject(By.text("Continue")).click() }

                detectObject(By.textContains("Enter a phone number to get a text"), IDLE_TIMEOUT * 100)
                        || throw IllegalStateException("Failed to wait for 'Enter phone number' prompt.")

                device.findObject(By.focused(true).clazz("android.widget.EditText")).text = account.phonenumber

                performWithRetry { device.findObject(By.text("Next")).click() }

                continue
            }

            // accept agb
            if(detectObject(By.text("I agree"))) {
                performWithRetry({ device.findObject(By.text("I agree")).click() }, recoverable = true, 50)
                Thread.sleep(IDLE_TIMEOUT)

                continue
            }

            // handle "make sure you can always sign in"
            // TODO


            // Here it can also happen that Google is asking to sync contacts
            if(detectObject(By.textContains("Never lose your contacts"))) {
                performWithRetry {
                    // for some reason, this text is not directly clickable.
                    val obj = device.findObject(By.textContains("turn on"))
                    device.click(obj.visibleBounds.centerX(), obj.visibleBounds.centerY()-10)
                }
                continue
            }

            // asking for recovery information
            if(detectObject(By.textContains("Add a recovery email"))) {
                performWithRetry{ device.findObject(By.text("Save")).click() }
                continue
            }

            // decline second factor question.
            if(detectObject(By.text("Not now"))) {
                performWithRetry{ device.findObject(By.text("Not now")).click() }
                continue
            }

            // decline adding a recovery phone number
            if(detectObject(By.text("Cancel"))) {
                performWithRetry{ device.findObject(By.text("Cancel")).click() }
                continue
            }

            // new "Who will be using this device?" thingy
            if(detectObject(By.textStartsWith("Who will be using this device?"))) {
                performWithRetry{ device.findObject(By.text("Next")).click() }
                continue
            }

            break
        }
    }

    fun loginAccount(email: String, handleCaptcha: Boolean) {
        Log.i(LTAG, "Initiating account login.")

        // initial test that the harvester server is reachable
        checkAlive()

        val account = getAccount(email)
            ?: throw IllegalStateException("Failed to retrieve account $email.")

        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        // check that we have wifi
        checkWIFIConnectivity()

        // this is device specific, therefore abstract
        openGoogleSettings()

        // sometimes the task fails and an account was logged in successfully
        // in this case, we just stop the task
        if(detectObject(By.text(account.email.lowercase()))) {
            Log.w(LTAG, "Account is already logged in, continuing...")
            // if the previous attempt failed, we have not yet logged the login of this account
            logAccountAction(email, getSerial(), "login")
            return
        }

        // A variant does no longer offer the "Recommended" tab for google services, but directly goes to
        // the services tab. There is no sign in button then, but rather one needs to click on a service to get to login
        if(!detectObject(By.textContains("Sign in"))) {
            Log.w(LTAG, "Sign in button not found, trying to click on subservices instead.")

            performWithRetry {
                device.findObject(By.textStartsWith("Search, Assistant")).click()
            }

            performWithRetry {
                device.findObject(By.text("Google Assistant")).click()
            }
        }


        // there are different UIs with Sign in ??
        if(detectObject(By.text("Sign In"))) {
            // if we hit the earlier case were the sign in button is not there, it is capitalized instead for some reason
            performWithRetry({ device.findObject(By.textContains("Sign In")).click() },
                false, 100)
        } else {
            // the reason why this fails is if the Google play services are currently being updated
            // we work around this issue by setting the retry number very high.
            performWithRetry({ device.findObject(By.textContains("Sign in")).click() },
                false, 100)
        }



        // sometimes there is a pin entry here?
        if(detectObject(By.text("Confirm PIN")) || detectObject(By.text("Re-enter your PIN"))) {
            enterPIN()
        }

        // wait for email prompt (can take some time)
        detectObject(By.text("Forgot email?"), IDLE_TIMEOUT * 50)
                || throw IllegalStateException("Failed to wait for 'Forgot email?' prompt.")

        // set "email or phone" field
        performWithRetry {
            device.findObject(By.clazz("android.widget.EditText")).text = email
        }
        Thread.sleep(IDLE_TIMEOUT)

        // click next button
        performWithRetry { device.findObject(By.text("Next")).click() }
        Thread.sleep(IDLE_TIMEOUT * 3) // might take some time for loading

        // Detect captcha to trigger a manual intervention.
        if(detectObject(By.text("I'm not a robot"))) {
            // we are already here because we noticed a captcha in the previous iteration
            if(handleCaptcha) {
                // at this point, the supervisor has to solve the captcha and hit next
                // we wait until we see the password field (up to one hour)
                if(detectObject(By.clazz("android.widget.EditText"), timeout = 1000L * 60L * 60L)) {
                    // we continue with next step (entering of the password)
                } else {
                    throw IllegalStateException("Could not find password field after waiting!")
                }
            } else {
                // inform supervisor of the captcha
                Log.e(LTAG, "Found captcha text, requiring a manual intervention.")
                throw IllegalStateException("CAPTCHA - Manual Intervention required.")
            }
        }

        // set password field
        performWithRetry {
            device.findObject(By.clazz("android.widget.EditText")).text = account.password
        }

        // if there was a captcha, we have to enter our phone number now
        if(detectObject(By.textContains("detected unusual activity on this account. Enter a phone number"),
                SHORT_WAIT)) {
            device.findObject(By.clazz("android.widget.EditText")).text = account.phonenumber

            // now we have to click "Get Code"
            performWithRetry { device.findObject(By.text("Get code")).click() }

            // wait (up to 15 minutes) until sms arrived (TODO: does this always transition to "I agree"?)
            if(!detectObject(By.text("I agree"), timeout = 1000L * 60 * 15)) {
               throw IllegalStateException("Failed to wait for SMS code!!")
            }
        } else {
            // click next button
            performWithRetry { device.findObject(By.text("Next")).click() }
            Thread.sleep(IDLE_TIMEOUT * 3) // might take some time for loading
        }

        // handle popups
        handleAccountDialogues(account)

        // On the S22 ultra, there is a "More" button first, scrolling down a few pixels.

        if(detectObject(By.text("More"))){
            try {
                performWithRetry({ device.findObject(By.text("More")).click() }, true, MAX_RETRIES)
            } catch(e: IllegalStateException) {
                // if it was not here, we can just continue
            }
        }

        // accept backups
        performWithRetry { device.findObject(By.text("Accept")).click() }

        detectObject(By.textContains("Manage your Google Account"), IDLE_TIMEOUT * 10)
                || detectObject(By.textContains("All services"), IDLE_TIMEOUT)
                || throw IllegalStateException("Failed to wait for settings screen after logging in the account.")

        logAccountAction(email, getSerial(), "login")

        // go back to main screen
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    open fun retrieveSMSCode(platform: Platform): String {
        throw NotImplementedError("retrieveSMSCode is only implemented for the G20 device.")
    }

    abstract fun setupWIFI()

    abstract fun installESIM(phonenumber: String)

    abstract fun disableCellular(phonenumber: String)

    abstract fun removeESIM(phonenumber: String)

    abstract fun disableSound()

    abstract fun disableScreenTimeout()

    abstract fun disableUpdates()

    abstract fun factoryReset()

    abstract fun openGoogleSettings()

    abstract fun enterPIN()

    abstract fun logoutAccount(email: String)
}

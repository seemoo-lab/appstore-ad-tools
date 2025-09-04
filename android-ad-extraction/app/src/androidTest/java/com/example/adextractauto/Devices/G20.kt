package com.example.adextractauto.Devices

import android.util.Log
import android.view.KeyEvent.KEYCODE_ENTER
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.example.adextractauto.checkAlive
import com.example.adextractauto.getSIMInfo
import com.example.adextractauto.logESIMInstall
import com.example.adextractauto.releaseESIM
import java.time.Instant
import java.util.NoSuchElementException

class G20(device: UiDevice) : AndroidDevice(device) {
    private var codeRetrievalRetryCounter = 0

    override fun checkWIFIConnectivity() {
        // for g20 device, ethernet might be connected for local account creation.
        // ethernet is not caught by getNetworkCapabilities, so we have to handle that manually
        if (device.executeShellCommand("ip route get 1.1.1.1").contains(" dev eth0 ")) {
            Log.i(LTAG, "Found ethernet connection, leaving checkWIFIConnectivity(.")
            return
        } else {
            super.checkWIFIConnectivity()
        }
    }

    override fun setupWIFI() {
        throw NotImplementedError("Not implemented.")
    }

    override fun disableSound() {
        throw NotImplementedError("Not implemented.")
    }

    override fun disableScreenTimeout() {
        throw NotImplementedError("Not implemented.")
    }

    override fun disableUpdates() {
        throw NotImplementedError("Not implemented.")
    }

    override fun factoryReset() {
        throw NotImplementedError("Not implemented.")
    }

    override fun openGoogleSettings() {
        throw NotImplementedError("Not implemented.")
    }

    override fun logoutAccount(email: String) {
        throw NotImplementedError("Not implemented.")
    }

    override fun enterPIN() {
        // there are different variants of pin prompts
        val descriptor = if(detectObject(By.desc("PIN"))) {
            By.desc("PIN")
        } else if(detectObject(By.res("com.samsung.android.biometrics.app.setting:id/lockPassword"))) {
            By.res("com.samsung.android.biometrics.app.setting:id/lockPassword")
        } else {
            throw IllegalStateException("Failed to wait for PIN element prompt.")
        }

        // enter pin (fails sometimes, therefore retry)
        performWithRetry {
            device.waitForIdle(IDLE_TIMEOUT)
            // set focus
            device.findObject(descriptor).click()
            device.findObject(descriptor).text = DEVICE_PIN
            Thread.sleep(IDLE_TIMEOUT)
            device.pressKeyCode(KEYCODE_ENTER)
            Thread.sleep(IDLE_TIMEOUT)

            // use implicit retry semantic of performRetry by throwing NPE
            if(detectObject(By.text("Confirm PIN"))) {
                throw NullPointerException()
            }
        }
    }

    /**
     * Helper function to deal with issues when opening settings (such as tip overlays).
     */
    private fun openSettings() {
        // try to clear previous state (partially entered creds, for example)
        device.executeShellCommand("am force-stop com.android.settings")

        device.executeShellCommand("am start -a $SETTINGS_IDENTIFIER")
        device.waitForIdle(IDLE_TIMEOUT)

        // sanity check that we really are in the settings main menu
        // and that nothing is obstructing our user interface
        var iterations = 0
        while(true) {
            if (!detectObject(By.text("Connections"))) {
                device.pressBack()
                device.waitForIdle(IDLE_TIMEOUT)
                device.pressBack()
                device.waitForIdle(IDLE_TIMEOUT)
                device.pressBack()
                device.waitForIdle(IDLE_TIMEOUT)
                device.pressBack()
                device.waitForIdle(IDLE_TIMEOUT)

                device.pressHome()
                device.executeShellCommand("am start -a $SETTINGS_IDENTIFIER")
                device.waitForIdle(IDLE_TIMEOUT)
            } else {
                break
            }

            if(iterations++ > 30) {
                throw IllegalStateException("Failed to open settings menu.")
            }
        }
    }

    override fun installESIM(phonenumber: String) {
        Log.i(LTAG, "Initiating installation of the ESIM.")

        // do this first to ensure that the screen is on before doing anything else
        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        // assert that we already have a wifi connection (or VPN for account creation purposes)
        checkWIFIConnectivity()

        // initial test that the harvester server is reachable
        checkAlive()

        // retrieve sim information
        val esim = getSIMInfo(phonenumber)
            ?: throw IllegalStateException("Could not retrieve eSIM with phonenumber $phonenumber")

        // if sim is locked, bail out
        if(esim.locked) {
            Log.e(LTAG, "Could not fetch eSIM details: eSIM is locked! Bailing out.")
            throw IllegalStateException("eSIM is in locked state.")
        }

        openSettings()

        performWithRetry { device.findObject(By.text("Connections")).click() }
        performWithRetry { device.findObject(By.text("SIM manager")).click() }

        // this takes some time usually, and we are close to the 30 iterations limit
        // so we add a manually wait. alternatively we could increase MAX_RETRIES for G20.
        performWithRetry {
            device.findObject(By.text("Add eSIM")).click()
            Thread.sleep(IDLE_TIMEOUT * 5)
        }

        // can take a long time if network is not ready
        detectObject(By.text("Scan QR code"), timeout= SHORT_WAIT * 180)
                || throw IllegalStateException("Failed to wait for QR code prompt.")
        device.waitForIdle(IDLE_TIMEOUT)
        performWithRetry { device.findObject(By.text("Scan QR code")).click() }
        performWithRetry { device.findObject(By.text("Enter activation code")).click() }

        // retry to enter if it fails
        for(i in 0..4) {
            // wait until code field is here
            detectObject(By.text("Enter activation code"), timeout= IDLE_TIMEOUT * 15)
                    || throw IllegalStateException("Failed to wait for activation code prompt.")
            Thread.sleep(IDLE_TIMEOUT) // fix issue where code is not fully entered
            performWithRetry { device.findObject(By.focused(true)).text = "LPA:1$${esim.address}$${esim.activationCode}" }
            Thread.sleep(IDLE_TIMEOUT) // fix issue where code is not fully entered
            performWithRetry { device.findObject(By.text("Done")).click() }
            Thread.sleep(IDLE_TIMEOUT) // fix issue where code is not fully entered

            // check if failed to enter
            if(detectObject(By.text("Enter activation code"))) {
                continue
            }

            break
        }

        // wait until "Enter code from service provider" is here
        detectObject(By.text("Enter code from service provider"), timeout= SHORT_WAIT * 180)
                || throw IllegalStateException("Failed to wait for service provider code prompt.")
        performWithRetry { device.findObject(
            By.clazz("android.widget.EditText")).text = esim.confirmationCode
        }
        performWithRetry { device.findObject(By.text("Done")).click() }

        // wait until esIM has been installed
        detectObject(By.text(ESIM_IDENTIFIER), SHORT_WAIT * 200)
                || throw IllegalStateException("Failed to wait for ESIM_IDENTIFIER text.")

        // log success
        logESIMInstall(phonenumber, getSerial(), Instant.now().toString())

        // go back to home screen
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun disableCellular(phonenumber: String) {
        throw NotImplementedError("Not implemented.")
    }

    override fun removeESIM(phonenumber: String) {
        Log.i(LTAG, "Initiating the removal of the ESIM.")

        // initial test that the harvester server is reachable
        checkAlive()

        // do this first to ensure that the screen is on before doing anything else
        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        fixScreenOrientation()

        device.executeShellCommand("am start -a android.settings.SETTINGS")
        device.waitForIdle(IDLE_TIMEOUT)

        performWithRetry { device.findObject(By.text("Connections")).click() }
        performWithRetry { device.findObject(By.text("SIM manager")).click() }
        performWithRetry { device.findObject(By.text("eSIM 1")).click() }
        performWithRetry { device.findObject(By.text("Remove")).click() }

        // enter pin
        enterPIN()

        performWithRetry { device.findObject(By.text("Remove")).click() }
        device.wait(Until.hasObject(By.text("Add eSIM")), IDLE_TIMEOUT)
            ?: throw IllegalStateException("Failed to wait for 'Add eSIM' text")

        // if everything worked, we can mark this sim as released
        releaseESIM(phonenumber)

        // go back to home screen
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
    }

    override fun retrieveSMSCode(platform: Platform): String {
        Log.i(LTAG, "Initiating SMS code retrieval for platform = $platform.")

        // do this first to ensure that the screen is on before doing anything else
        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        // clear previous state (does not really always work)
        device.executeShellCommand("am force-stop com.samsung.android.messaging")

        // open messaging app
        device.executeShellCommand("am start com.samsung.android.messaging")
        device.waitForIdle(IDLE_TIMEOUT)

        // sometimes we remain in the wrong screen, so go back and re-open
        // go back to home screen
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)

        // open messaging app
        device.executeShellCommand("am start com.samsung.android.messaging")
        device.waitForIdle(IDLE_TIMEOUT)


        val code:String = try {
            when(platform) {
                Platform.Google -> {
                    performWithRetry { device.findObject(By.descContains("Google")).click() }

                    device.findObjects(By.textContains("is your Google verification code")).last().text.split(" ").first()
                }

                Platform.Apple -> {
                    performWithRetry { device.findObject(By.descContains("Apple")).click() }

                    device.findObjects(By.textContains("Your Apple Account code is:")).last().text.split(" ")[5].replace(".", "")
                }
            }
        } catch(e: NoSuchElementException) {
            // just retry, sometimes the wrong message is clicked
            if(codeRetrievalRetryCounter++ > 30) {
                throw IllegalStateException("Failed to retrieve code after 30 attempts.")
            }
            return retrieveSMSCode(platform)
        }

        // go back to home screen
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)
        device.pressBack()
        device.waitForIdle(IDLE_TIMEOUT)

        // reset retry counter
        codeRetrievalRetryCounter = 0

        // use exception as an easy way to communicate the result
        throw IllegalArgumentException(">>>>$code<<<<")
    }
}

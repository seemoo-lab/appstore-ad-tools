package com.example.adextractauto.Devices

import android.util.Log
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiScrollable
import androidx.test.uiautomator.UiSelector
import com.example.adextractauto.logAccountAction

class G24(device: UiDevice) : G23(device) {

    // copied from G23 device, mostly some textual changes
    override fun factoryReset() {
        Log.i(LTAG, "Initiating factory reset.")

        if(!device.isScreenOn) unlockDevice()
        device.pressHome()

        openSettings()

        // get root scrollable container and scroll to end
        performWithRetry {
            assert(UiScrollable(UiSelector().scrollable(true).className("androidx.recyclerview.widget.RecyclerView")).flingToEnd(100))
        }

        // open general device management
        performWithRetry { device.findObject(By.text("General management")).click() }

        // get root scrollable container and scroll to end
        performWithRetry {
            assert(UiScrollable(UiSelector().scrollable(true).className("androidx.recyclerview.widget.RecyclerView")).scrollToEnd(100))
        }

        performWithRetry { device.findObject(By.text("Reset")).click() }

        // get root scrollable container and scroll to end
        performWithRetry {
            assert(UiScrollable(UiSelector().scrollable(true)).scrollToEnd(100))
        }

        performWithRetry { device.findObject(By.text("Factory data reset")).click() }

        // get root scrollable container and scroll to end (this is for some reason no RecyclerView)
        detectObject(By.textContains("This will erase all data"))
                || throw IllegalStateException("Failed to find reset text.")

        // if there was an account logged in, there can be more content and a scroll down is required.
        if(detectObject(By.scrollable(true).clazz("android.widget.ScrollView"), SHORT_WAIT)) {
            performWithRetry {
                assert(UiScrollable(UiSelector().scrollable(true).className("android.widget.ScrollView")).flingToEnd(100))
            }
        }

        // select eSIms for deletion (in case earlier eject has gone wrong, is not always there)
        try {
            performWithRetry({device.findObject(By.text("eSIMs")).click()},
                true, 10)
        } catch(e: IllegalStateException) {
            // It's fine if there is no eSIMs button
        }
        performWithRetry { device.findObject(By.text("Reset")).click() }
        enterPIN()

        performWithRetry { device.findObject(By.text("Delete all")).click() }

        logAccountAction("PREV_ACC", getSerial(), "logout (factory reset)")

        // try to click the "remove esim" thingy (fails sometimes?)
        var iterations = 0
        while(detectObject(By.text("Remove all eSIMs?"))) {
            performWithRetry {device.findObject(By.text("Remove")).click() }
            if(iterations++ > 30)
                throw IllegalStateException("Exceeded 30 iterations when trying to confirm sim removal during reset.")
            // dialogue re-appears sometimes
            Thread.sleep(1000)
        }

        // we want to fail if the devices is not starting to reset now.
        Thread.sleep(5000)
        throw java.lang.IllegalStateException("Device still up, even though it should start resetting!")
    }
}
package com.example.foo.testcrowdin

import android.app.Application
import com.crowdin.platform.Crowdin
import com.crowdin.platform.CrowdinConfig

class App : Application() {
    override fun onCreate() {
        super.onCreate()
        Crowdin.init(
            applicationContext,
            CrowdinConfig.Builder()
                .withDistributionHash(BuildConfig.CROWDIN_DISTRIBUTION_HASH)
                .build()
        )
    }
}

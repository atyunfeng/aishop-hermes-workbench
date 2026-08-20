plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "com.aishop.worker"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.aishop.worker"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        val storePath = System.getenv("AISHOP_SIGNING_STORE_FILE")
        val storePasswordValue = System.getenv("AISHOP_SIGNING_STORE_PASSWORD")
        val keyAliasValue = System.getenv("AISHOP_SIGNING_KEY_ALIAS")
        val keyPasswordValue = System.getenv("AISHOP_SIGNING_KEY_PASSWORD")
        if (listOf(storePath, storePasswordValue, keyAliasValue, keyPasswordValue).all { !it.isNullOrBlank() }) {
            create("production") {
                storeFile = file(storePath!!)
                storePassword = storePasswordValue
                keyAlias = keyAliasValue
                keyPassword = keyPasswordValue
            }
        }
    }

    buildTypes {
        getByName("release") {
            signingConfig = signingConfigs.findByName("production")
        }
    }

    flavorDimensions += "environment"
    productFlavors {
        create("demo") {
            dimension = "environment"
            applicationIdSuffix = ".demo"
            versionNameSuffix = "-demo"
            buildConfigField("boolean", "ALLOW_CLEARTEXT", "true")
        }
        create("production") {
            dimension = "environment"
            buildConfigField("boolean", "ALLOW_CLEARTEXT", "false")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

tasks.register("verifyProductionSigning") {
    doLast {
        if (System.getenv("AISHOP_REQUIRE_SIGNING") == "true" &&
            android.signingConfigs.findByName("production") == null
        ) {
            throw GradleException(
                "Production signing required: configure AISHOP_SIGNING_STORE_FILE, " +
                    "AISHOP_SIGNING_STORE_PASSWORD, AISHOP_SIGNING_KEY_ALIAS and " +
                    "AISHOP_SIGNING_KEY_PASSWORD",
            )
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")

    val composeBom = platform("androidx.compose:compose-bom:2026.08.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

    testImplementation("junit:junit:4.13.2")
}

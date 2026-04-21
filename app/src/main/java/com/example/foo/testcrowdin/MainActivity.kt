package com.example.foo.testcrowdin

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.adaptive.navigationsuite.NavigationSuiteScaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.UnderlineSpan
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextDecoration
import androidx.core.text.HtmlCompat
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.tooling.preview.PreviewScreenSizes
import androidx.compose.ui.unit.dp
import com.example.foo.testcrowdin.ui.theme.TestCrowdinTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TestCrowdinTheme {
                TestCrowdinApp()
            }
        }
    }
}

@PreviewScreenSizes
@Composable
fun TestCrowdinApp() {
    var currentDestination by rememberSaveable { mutableStateOf(AppDestinations.HOME) }

    NavigationSuiteScaffold(
        navigationSuiteItems = {
            AppDestinations.entries.forEach {
                item(
                    icon = {
                        Icon(
                            painterResource(it.icon),
                            contentDescription = it.label
                        )
                    },
                    label = { Text(it.label) },
                    selected = it == currentDestination,
                    onClick = { currentDestination = it }
                )
            }
        }
    ) {
        Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
            Greeting(
                name = "Android ${currentDestination.label}",
                modifier = Modifier
                    .padding(innerPadding)
                    .padding(all = 16.dp)
            )
        }
    }
}

enum class AppDestinations(
    val label: String,
    val icon: Int,
) {
    HOME("Home", R.drawable.ic_home),
    FAVORITES("Favorites", R.drawable.ic_favorite),
    PROFILE("Profile", R.drawable.ic_account_box),
}

@Composable
fun Greeting(name: String, modifier: Modifier = Modifier) {
    Column(modifier = modifier) {
        Text(text = "Hello $name!")
        Text(text = stringResource(R.string.onboarding_verify_email_otp_label))
        FamilyCountryLabel()
        LoginTermsDescription()
        LoginAppleButton()
    }
}

@Composable
fun FamilyCountryLabel(modifier: Modifier = Modifier) {
    val rawString = stringResource(R.string.onboarding_create_family_family_country_label)
    val plainText = HtmlCompat.fromHtml(rawString, HtmlCompat.FROM_HTML_MODE_COMPACT).toString()
    Text(text = plainText, modifier = modifier)
}

fun Spanned.toAnnotatedString(): AnnotatedString = buildAnnotatedString {
    append(this@toAnnotatedString.toString())
    getSpans(0, length, UnderlineSpan::class.java).forEach { span ->
        addStyle(
            SpanStyle(textDecoration = TextDecoration.Underline),
            getSpanStart(span),
            getSpanEnd(span)
        )
    }
}

@Composable
fun LoginTermsDescription(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val annotatedString = remember {
        val ssb = SpannableStringBuilder(context.resources.getText(R.string.onboarding_login_terms_description))
        val placeholder = ssb.indexOf("%s")
        if (placeholder >= 0) ssb.replace(placeholder, placeholder + 2, "Terms & Conditions")
        (ssb as Spanned).toAnnotatedString()
    }
    Text(text = annotatedString, modifier = modifier)
}

@Composable
fun LoginAppleButton(modifier: Modifier = Modifier) {
    Button(
        onClick = {},
        modifier = modifier
    ) {
        Text(text = stringResource(R.string.onboarding_login_apple_button))
    }
}

@Preview(showBackground = true)
@Composable
fun GreetingPreview() {
    TestCrowdinTheme {
        Greeting("Android")
    }
}
package com.quotoex

import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONArray
import org.json.JSONObject

class MainActivity : AppCompatActivity() {

    private val handler = Handler(Looper.getMainLooper())

    private lateinit var statusLabel: TextView
    private lateinit var balanceLabel: TextView
    private lateinit var emailInput: EditText
    private lateinit var passInput: EditText
    private lateinit var loginBtn: Button
    private lateinit var assetSpinner: Spinner
    private lateinit var amountInput: EditText
    private lateinit var logLabel: TextView
    private lateinit var ordersList: LinearLayout

    private var pyModule: com.chaquo.python.PyObject? = null
    private val orders = mutableListOf<String>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // تهيئة Python
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
        pyModule = Python.getInstance().getModule("main")

        buildUI()
    }

    private fun buildUI() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(30, 80, 30, 30)
            setBackgroundColor(Color.parseColor("#0D1117"))
        }

        statusLabel = TextView(this).apply {
            text = "Ready"
            textSize = 14f
            setTextColor(Color.parseColor("#8B949E"))
            gravity = Gravity.CENTER
        }
        root.addView(statusLabel, lp())

        balanceLabel = TextView(this).apply {
            text = "Balance: --"
            textSize = 18f
            setTextColor(Color.parseColor("#2ECC71"))
            gravity = Gravity.CENTER
            setPadding(0, 10, 0, 20)
        }
        root.addView(balanceLabel, lp())

        root.addView(label("Email"))
        emailInput = EditText(this).apply {
            hint = "your@email.com"
            inputType = InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            setBackgroundColor(Color.parseColor("#161B22"))
            setPadding(16, 16, 16, 16)
        }
        root.addView(emailInput, lp())

        root.addView(label("Password"))
        passInput = EditText(this).apply {
            hint = "Password"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            setBackgroundColor(Color.parseColor("#161B22"))
            setPadding(16, 16, 16, 16)
        }
        root.addView(passInput, lp())

        loginBtn = Button(this).apply {
            text = "Login (Demo)"
            setBackgroundColor(Color.parseColor("#1F6FEB"))
            setTextColor(Color.WHITE)
            textSize = 16f
            setOnClickListener { doLogin() }
        }
        root.addView(loginBtn, lp(60))

        root.addView(label("Asset"))
        assetSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(
                this@MainActivity,
                android.R.layout.simple_spinner_dropdown_item,
                listOf(
                    "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc",
                    "BTCUSD_otc", "ETHUSD_otc", "XAUUSD_otc"
                )
            )
        }
        root.addView(assetSpinner, lp())

        root.addView(label("Amount ($)"))
        amountInput = EditText(this).apply {
            setText("1")
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#161B22"))
            setPadding(16, 16, 16, 16)
        }
        root.addView(amountInput, lp())

        val btnRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 20, 0, 0)
        }
        val buyBtn = Button(this).apply {
            text = "BUY (Call)"
            setBackgroundColor(Color.parseColor("#2ECC71"))
            setTextColor(Color.WHITE)
            setOnClickListener { doTrade("call") }
        }
        btnRow.addView(buyBtn, LinearLayout.LayoutParams(
            0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f
        ).apply { marginEnd = 8 })

        val sellBtn = Button(this).apply {
            text = "SELL (Put)"
            setBackgroundColor(Color.parseColor("#E74C3C"))
            setTextColor(Color.WHITE)
            setOnClickListener { doTrade("put") }
        }
        btnRow.addView(sellBtn, LinearLayout.LayoutParams(
            0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f
        ).apply { marginStart = 8 })
        root.addView(btnRow, lp())

        root.addView(label("Orders"))
        ordersList = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        val ordersScroll = ScrollView(this).apply {
            addView(ordersList)
        }
        root.addView(ordersScroll, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 200
        ).apply { topMargin = 10 })

        root.addView(label("Log"))
        logLabel = TextView(this).apply {
            textSize = 10f
            setTextColor(Color.parseColor("#8B949E"))
            typeface = android.graphics.Typeface.MONOSPACE
        }
        val logScroll = ScrollView(this).apply {
            addView(logLabel)
        }
        root.addView(logScroll, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 300
        ))

        setContentView(ScrollView(this).apply { addView(root) })
    }

    private fun lp(height: Int = ViewGroup.LayoutParams.WRAP_CONTENT)
        = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, height
        )

    private fun label(text: String) = TextView(this).apply {
        this.text = text
        textSize = 13f
        setTextColor(Color.WHITE)
        setPadding(0, 14, 0, 6)
    }

    private fun doLogin() {
        val email = emailInput.text.toString().trim()
        val password = passInput.text.toString()
        if (email.isBlank() || password.isBlank()) {
            toast("Enter email and password")
            return
        }
        log("Login: $email")
        statusLabel.text = "Connecting..."

        Thread {
            try {
                pyModule?.callAttr("init_callbacks",
                    PyCallback(this@MainActivity))
                pyModule?.callAttr("login", email, password)
            } catch (e: Exception) {
                handler.post { log("❌ ${e.message}") }
            }
        }.start()
    }

    private fun doTrade(direction: String) {
        val asset = assetSpinner.selectedItem.toString()
        val amount = amountInput.text.toString().toDoubleOrNull() ?: 1.0
        log("Trade: $direction $asset \$$amount")
        Thread {
            try {
                pyModule?.callAttr("buy", asset, amount, direction)
            } catch (e: Exception) {
                handler.post { log("❌ ${e.message}") }
            }
        }.start()
    }

    fun onPythonLog(msg: String) {
        handler.post {
            log(msg)
            runOnUiThread {
                statusLabel.text = msg.take(60)
            }
        }
    }

    fun onAuth(ok: Boolean) {
        handler.post {
            loginBtn.text = if (ok) "✅ Logged in" else "Login failed"
        }
    }

    fun onOrder(kind: String, id: String, profit: Double) {
        handler.post {
            val line = when (kind) {
                "open" -> "🟢 Open: $id"
                "close" -> if (profit >= 0) "✅ Win \$$profit" else "❌ Loss \$$profit"
                "error" -> "⚠️ $id"
                else -> "$kind: $id"
            }
            orders.add(0, line)
            ordersList.removeAllViews()
            orders.take(10).forEach {
                ordersList.addView(TextView(this@MainActivity).apply {
                    text = it
                    textSize = 12f
                    setTextColor(Color.WHITE)
                    setPadding(0, 4, 0, 4)
                })
            }
        }
    }

    private fun log(msg: String) {
        logLabel.append("\n$msg")
    }

    private fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
    }
}

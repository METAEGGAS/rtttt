package com.quotoex

import android.os.Bundle
import android.view.Gravity
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        val tv = TextView(this).apply {
            text = "✅ التطبيق اشتغل\n\nلو شفت الرسالة دي،\nالمشكلة في Python Runtime."
            textSize = 22f
            gravity = Gravity.CENTER
            setPadding(50, 200, 50, 50)
        }
        setContentView(tv)
    }
}

package com.quotoex

/**
 * جسر بين Python و MainActivity
 * Chaquopy بيستخدم reflection عشان ينادي الدوال دي
 */
class PyCallback(private val activity: MainActivity) {

    fun onPythonLog(msg: String) {
        activity.onPythonLog(msg)
    }

    fun onAuth(ok: Boolean) {
        activity.onAuth(ok)
    }

    fun onOrder(kind: String, id: String, profit: Double) {
        activity.onOrder(kind, id, profit)
    }
}

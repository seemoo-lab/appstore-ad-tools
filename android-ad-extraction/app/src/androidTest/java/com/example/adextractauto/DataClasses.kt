package com.example.adextractauto

import com.google.gson.annotations.SerializedName

// Class for holding ads
data class Ad(
    @SerializedName("id") val id: Int,
    @SerializedName("experiment_id") val experimentId: Int,
    @SerializedName("label") val name: String,
    @SerializedName("sub_label") val subLabel: String,
    @SerializedName("time") val timestamp: String,
    @SerializedName("type") val type: String) {

    // define equality only by name. helpful for membership tests.
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is Ad) return false

        if (name != other.name) return false

        return true
    }

    // auto generated
    override fun hashCode(): Int {
        var result = name.hashCode()
        result = 31 * result + timestamp.hashCode()
        return result
    }
}

data class ID(@SerializedName("id") val id: Int)
data class AppInstall(@SerializedName("email") val email: String,
                      @SerializedName("app_id") val appId: String,
                      @SerializedName("time") val time: String)
data class App(val id: Int,
               @SerializedName("google_id") val googleId: String,
               @SerializedName("apple_id") val appleId: String,
               @SerializedName("name") val name: String)
data class Account(val email: String,
                   @SerializedName("sur_name") val surName: String,
                   @SerializedName("first_name") val firstName: String,
                   val password: String,
                   val birth: String,
                   val gender: String,
                   val phonenumber: String,
                   val street: String,
                   val city: String,
                   val postalcode: Int,
                   @SerializedName("street_number") val streetNumber: Int,
                   val country: String,
                   @SerializedName("persona_id") val personaId: Int)
data class SIM(val phonenumber: String,
               val address: String,
               @SerializedName("activation_code") val activationCode: String,
               @SerializedName("confirmation_code") val confirmationCode: String,
               val pin: Int,
               val pul: Int,
               @SerializedName("sim_number") val simNumber: Long,
               val locked: Boolean,
               val comment: String)

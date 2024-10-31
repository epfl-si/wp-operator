<?php

class WPForms extends Plugin
{
	protected $pluginPath = "wpforms/wpforms.php";
	private $wpforms_challenge = 'a:11:{s:6:"status";s:7:"skipped";s:4:"step";i:0;s:7:"user_id";i:1;s:7:"form_id";i:0;s:10:"embed_page";i:0;s:16:"started_date_gmt";s:19:"2020-07-08 07:47:17";s:17:"finished_date_gmt";s:19:"2020-07-08 07:47:17";s:13:"seconds_spent";i:0;s:12:"seconds_left";i:300;s:13:"feedback_sent";b:0;s:19:"feedback_contact_me";b:0;}';
	# Use the global CSS and enable GDPR options (GDPR Enhancements, Disable User Cookies, Disable User Details)
	private $wpforms_settings = 'a:19:{s:8:"currency";s:3:"CHF";s:18:"hide-announcements";b:1;s:14:"hide-admin-bar";b:1;s:14:"uninstall-data";b:0;s:23:"email-summaries-disable";b:0;s:11:"disable-css";s:1:"1";s:13:"global-assets";b:0;s:4:"gdpr";b:1;s:17:"gdpr-disable-uuid";b:1;s:20:"gdpr-disable-details";b:1;s:11:"email-async";b:0;s:14:"email-template";s:7:"default";s:18:"email-header-image";s:76:"https://www.epfl.ch/wp-content/themes/wp-theme-2018/assets/svg/epfl-logo.svg";s:22:"email-background-color";s:7:"#e9eaec";s:17:"email-carbon-copy";b:0;s:13:"modern-markup";s:1:"0";s:20:"modern-markup-is-set";b:1;s:29:"stripe-webhooks-communication";s:4:"curl";s:16:"stripe-card-mode";s:7:"payment";}';
	# Set the WPForms license
	private $wpforms_license = 'a:6:{i:0;s:0:"";s:3:"key";s:32:"{{ lookup("env_secrets", "wp_plugin_wpforms", "WPFORMS_LICENSE") }}";s:4:"type";s:5:"elite";s:10:"is_expired";b:0;s:11:"is_disabled";b:0;s:10:"is_invalid";b:0;}';

	public function updateOptions()
	{
		update_option( 'wpforms_challenge', $this->wpforms_challenge);
		update_option( 'wpforms_settings', $this->wpforms_settings);
		update_option( 'wpforms_license', $this->wpforms_license);
	}
}

<?php

class WPForms extends Plugin
{
	protected $pluginPath = "wpforms/wpforms.php";
	private $wpforms_challenge = array (
		'status' => 'skipped',
		'step' => 0,
		'user_id' => 1,
		'form_id' => 0,
		'embed_page' => 0,
		'started_date_gmt' => '2020-07-08 07:47:17',
		'finished_date_gmt' => '2020-07-08 07:47:17',
		'seconds_spent' => 0,
		'seconds_left' => 300,
		'feedback_sent' => false,
		'feedback_contact_me' => false,
	);
	# Use the global CSS and enable GDPR options (GDPR Enhancements, Disable User Cookies, Disable User Details)
	private $wpforms_settings = array (
		'currency' => 'CHF',
		'hide-announcements' => true,
		'hide-admin-bar' => true,
		'uninstall-data' => false,
		'email-summaries-disable' => false,
		'disable-css' => '1',
		'global-assets' => false,
		'gdpr' => true,
		'gdpr-disable-uuid' => true,
		'gdpr-disable-details' => true,
		'email-async' => false,
		'email-template' => 'default',
		'email-header-image' => 'https://www.epfl.ch/wp-content/themes/wp-theme-2018/assets/svg/epfl-logo.svg',
		'email-background-color' => '#e9eaec',
		'email-carbon-copy' => false,
		'modern-markup' => '0',
		'modern-markup-is-set' => true,
		'stripe-webhooks-communication' => 'curl',
		'stripe-card-mode' => 'payment',
	);
	# Set the WPForms license
	private function get_wpforms_license_option() {
		$wpforms_license = $this->getSecretValue('wpform_license');
		return array (
			'key' => $wpforms_license,
			'type' => 'elite',
			'is_expired' => false,
			'is_disabled' => false,
			'is_invalid' => false,
		);
	}
	public function updateOptions()
	{
		update_option( 'wpforms_challenge', $this->wpforms_challenge);
		update_option( 'wpforms_settings', $this->wpforms_settings);
		update_option( 'wpforms_license', $this->get_wpforms_license_option());
	}
}

<?php

class Payonline extends Plugin
{
	protected $pluginPath = "wpforms-epfl-payonline/wpforms-epfl-payonline.php";
	# Saferpay secrets
	private $wpforms_epfl_payonline_saferpay_apiusername_test = "{{ saferpay.test.apiusername | eyaml(eyaml_keys) }}";
	private $wpforms_epfl_payonline_saferpay_apipassword_test = "{{ saferpay.test.apipassword | eyaml(eyaml_keys) }}";
	private $wpforms_epfl_payonline_saferpay_customerid_test = "{{ saferpay.test.customerid | eyaml(eyaml_keys) }}";
	private $wpforms_epfl_payonline_saferpay_terminalid_test = "{{ saferpay.test.terminalid | eyaml(eyaml_keys) }}";
	private $wpforms_epfl_payonline_saferpay_apiusername_prod = "{{ saferpay.prod.apiusername | eyaml(eyaml_keys) }}";
	private $wpforms_epfl_payonline_saferpay_apipassword_prod = "{{ saferpay.prod.apipassword | eyaml(eyaml_keys) }}";
	private $wpforms_epfl_payonline_saferpay_customerid_prod = "{{ saferpay.prod.customerid | eyaml(eyaml_keys) }}";
	private $wpforms_epfl_payonline_saferpay_terminalid_prod = "{{ saferpay.prod.terminalid | eyaml(eyaml_keys) }}";

	public function updateOptions()
	{
		update_option( 'wpforms-epfl-payonline-saferpay-apiusername-test', $this->wpforms_epfl_payonline_saferpay_apiusername_test);
		update_option( 'wpforms-epfl-payonline-saferpay-apipassword-test', $this->wpforms_epfl_payonline_saferpay_apipassword_test);
		update_option( 'wpforms-epfl-payonline-saferpay-customerid-test', $this->wpforms_epfl_payonline_saferpay_customerid_test);
		update_option( 'wpforms-epfl-payonline-saferpay-terminalid-test', $this->wpforms_epfl_payonline_saferpay_terminalid_test);
		update_option( 'wpforms-epfl-payonline-saferpay-apiusername-prod', $this->wpforms_epfl_payonline_saferpay_apiusername_prod);
		update_option( 'wpforms-epfl-payonline-saferpay-apipassword-prod', $this->wpforms_epfl_payonline_saferpay_apipassword_prod);
		update_option( 'wpforms-epfl-payonline-saferpay-customerid-prod', $this->wpforms_epfl_payonline_saferpay_customerid_prod);
		update_option( 'wpforms-epfl-payonline-saferpay-terminalid-prod', $this->wpforms_epfl_payonline_saferpay_terminalid_prod);
	}
}

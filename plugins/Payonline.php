<?php

class Payonline extends Plugin
{
	protected $pluginPath = "wpforms-epfl-payonline/wpforms-epfl-payonline.php";
	# Saferpay secrets
	private function wpforms_epfl_payonline_saferpay_apiusername_test() {
		return $this->getSecretValue('saferpay_test_apiusername');
	}
	private function wpforms_epfl_payonline_saferpay_apipassword_test() {
		return $this->getSecretValue('saferpay_test_apipassword');
	}
	private function wpforms_epfl_payonline_saferpay_customerid_test() {
		return $this->getSecretValue('saferpay_test_customerid');
	}
	private function wpforms_epfl_payonline_saferpay_terminalid_test() {
	return $this->getSecretValue('saferpay_test_terminalid');
}
	private function wpforms_epfl_payonline_saferpay_apiusername_prod() {
	return $this->getSecretValue('saferpay_prod_apiusername');
}
	private function wpforms_epfl_payonline_saferpay_apipassword_prod() {
		return $this->getSecretValue('saferpay_prod_apipassword');
	}
	private function wpforms_epfl_payonline_saferpay_customerid_prod() {
		return $this->getSecretValue('saferpay_prod_customerid');
	}
	private function wpforms_epfl_payonline_saferpay_terminalid_prod() {
		return $this->getSecretValue('saferpay_prod_terminalid');
	}

	public function updateOptions()
	{
		update_option( 'wpforms-epfl-payonline-saferpay-apiusername-test', $this.$this->wpforms_epfl_payonline_saferpay_apiusername_test());
		update_option( 'wpforms-epfl-payonline-saferpay-apipassword-test', $this.$this->wpforms_epfl_payonline_saferpay_apipassword_test());
		update_option( 'wpforms-epfl-payonline-saferpay-customerid-test', $this.$this->wpforms_epfl_payonline_saferpay_customerid_test());
		update_option( 'wpforms-epfl-payonline-saferpay-terminalid-test', $this.$this->wpforms_epfl_payonline_saferpay_terminalid_test());

		update_option( 'wpforms-epfl-payonline-saferpay-apiusername-prod', $this.$this->wpforms_epfl_payonline_saferpay_apiusername_prod());
		update_option( 'wpforms-epfl-payonline-saferpay-apipassword-prod', $this.$this->wpforms_epfl_payonline_saferpay_apipassword_prod());
		update_option( 'wpforms-epfl-payonline-saferpay-customerid-prod', $this.$this->wpforms_epfl_payonline_saferpay_customerid_prod());
		update_option( 'wpforms-epfl-payonline-saferpay-terminalid-prod', $this.$this->wpforms_epfl_payonline_saferpay_terminalid_prod());
	}
}

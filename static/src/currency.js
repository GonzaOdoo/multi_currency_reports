/** @odoo-module **/
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";
import { AgedPartnerBalanceFilters } from "@account_reports/components/aged_partner_balance/filters";
import { patch } from "@web/core/utils/patch";

const currencyFilterMethods = {
    async onSelectCurrencyGroup(currencyGroup) {
        const newGroupId = this.selectedCurrencyGroupId === currencyGroup.id ? false : currencyGroup.id;

        if (this.controller.cachedFilterOptions.selected_currency_group_id === newGroupId) {
            return;
        }

        await this.filterClicked({
            optionKey: "selected_currency_group_id",
            optionValue: newGroupId,
            reload: true,
        });
    },
    async setOnlyUsd(enabled) {
        if (this.controller.cachedFilterOptions.only_usd === enabled) {
            return;
        }
        await this.filterClicked({
            optionKey: "only_usd",
            optionValue: enabled,
            reload: true,
        });
    },
    isCurrencyGroupSelected(currencyGroup) {
        return this.selectedCurrencyGroupId === currencyGroup.id;
    },
    get selectedCurrencyGroupId() {
        return this.controller.cachedFilterOptions.selected_currency_group_id || false;
    },
    get onlyUsd() {
        return this.controller.cachedFilterOptions.only_usd || false;
    },
};

patch(AccountReportFilters.prototype, currencyFilterMethods);
patch(AgedPartnerBalanceFilters.prototype, currencyFilterMethods);